"""Questions about the code in, cited answers out.

    retrieval (named symbols, vectors, keywords, graph facts) -> answerer (streamed)
    -> verified citations -> message and usage stored

`ask` yields events the route sends as server-sent events (`sources`, `delta`, `done`, or
`error`), or collects into one JSON response.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.ai.answerer import Answerer, AnswerRequest
from codeagent.ai.chat import Usage
from codeagent.ai.citations import extract_citations
from codeagent.ai.prompts import Turn, standalone_question
from codeagent.core import metrics
from codeagent.core.errors import AppError, ForbiddenError, NotFoundError, error_body
from codeagent.core.ids import uuid7
from codeagent.core.logging import get_logger
from codeagent.models import Conversation, Message, Repository, UsageEvent, Workspace
from codeagent.models.enums import MessageRole, UsageKind
from codeagent.repositories.conversations import ConversationRepository
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.usage import UsageRepository
from codeagent.schemas.workspaces import WorkspaceSettings
from codeagent.services.container import Container
from codeagent.services.principal import Principal
from codeagent.services.retrieval import RetrievalService

log = get_logger("codeagent.ask")
DEFAULT_TITLE = "New question"
NO_REPOSITORIES = (
    "There is no indexed repository to answer from yet. Connect a repository on the "
    "Repositories page first."
)


@dataclass(frozen=True, slots=True)
class AskEvent:
    event: str
    data: dict[str, Any]
    # The exception behind an "error" event, so a JSON response keeps its status code.
    error: AppError | None = field(default=None, compare=False, repr=False)

    @classmethod
    def failure(cls, exc: AppError) -> AskEvent:
        return cls("error", error_body(exc.code, exc.message), exc)


def _title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= 80 else text[:77].rsplit(" ", 1)[0] + "..."


class AskService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.conversations = ConversationRepository(session)
        self.repos = ReposRepository(session)

    async def resolve_repository(
        self, workspace_id: uuid.UUID, ref: str | None
    ) -> Repository | None:
        if not ref:
            return None
        repository = await self.repos.by_ref(workspace_id, ref)
        if repository is None:
            raise NotFoundError("Repository not found.")
        return repository

    async def create_conversation(
        self, workspace: Workspace, principal: Principal, title: str | None, repository: str | None
    ) -> Conversation:
        if principal.user is None:
            raise ForbiddenError("API keys cannot own conversations. Use the ask endpoint.")
        scoped = await self.resolve_repository(workspace.id, repository)
        conversation = await self.conversations.add(
            Conversation(
                workspace_id=workspace.id,
                user_id=principal.user.id,
                repository_id=scoped.id if scoped else None,
                title=(title or DEFAULT_TITLE).strip()[:200],
            )
        )
        await self.session.commit()
        return conversation

    async def get_conversation(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID, principal: Principal
    ) -> Conversation:
        if principal.user is None:
            raise NotFoundError("Conversation not found.")
        conversation = await self.conversations.get(
            workspace_id, conversation_id, principal.user.id
        )
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def list_conversations(
        self, workspace_id: uuid.UUID, principal: Principal, *, limit: int, offset: int
    ) -> list[Conversation]:
        if principal.user is None:
            return []
        return await self.conversations.recent(
            workspace_id, principal.user.id, limit=limit, offset=offset
        )

    async def rename(self, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title.strip()[:200]
        await self.session.commit()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self.session.delete(conversation)
        await self.session.commit()

    async def messages(self, conversation: Conversation) -> list[Message]:
        return await self.conversations.messages(conversation.id)

    def _answerer(self, workspace: Workspace) -> Answerer:
        settings = WorkspaceSettings.model_validate(workspace.settings or {})
        return self.c.answerer if settings.agent_mode == "auto" else self.c.local_answerer

    async def ask(
        self,
        workspace: Workspace,
        principal: Principal,
        question: str,
        *,
        conversation: Conversation | None = None,
        repository: Repository | None = None,
    ) -> AsyncGenerator[AskEvent]:
        started = time.perf_counter()
        question = question.strip()
        answerer = self._answerer(workspace)
        scope_id = (
            conversation.repository_id
            if conversation is not None
            else (repository.id if repository else None)
        )

        history: list[Turn] = []
        if conversation is not None:
            previous = await self.conversations.messages(conversation.id, limit=40)
            history = [Turn(m.role, m.content) for m in previous[-6:]]
            if conversation.message_count == 0 and conversation.title == DEFAULT_TITLE:
                conversation.title = _title(question)
            user_message = await self.conversations.add_message(
                Message(conversation_id=conversation.id, role=MessageRole.USER, content=question)
            )
            await self.session.commit()
            yield AskEvent("user_message", {"id": str(user_message.id), "content": question})

        standalone = standalone_question(question, history)
        retrieval = RetrievalService(self.c, self.session)
        scopes = await retrieval.scopes(workspace.id, [scope_id] if scope_id else None)
        retrieved = await retrieval.for_question(
            workspace.id, scopes, standalone, limit=self.c.settings.answer_sources
        )
        sources_public = [s.public() for s in retrieved.sources]
        yield AskEvent("sources", {"sources": sources_public})

        usage = Usage()
        parts: list[str] = []
        if not scopes:
            parts.append(NO_REPOSITORIES)
            yield AskEvent("delta", {"text": NO_REPOSITORIES})
        else:
            request = AnswerRequest(
                standalone, retrieved.sources, retrieved.facts, retrieved.focus, history
            )
            try:
                async for delta in answerer.stream(request, usage):
                    parts.append(delta)
                    yield AskEvent("delta", {"text": delta})
            except AppError as exc:
                log.warning("answer_failed", code=exc.code)
                yield AskEvent.failure(exc)
                return
        answer, citations = extract_citations("".join(parts), retrieved.sources)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage_payload = {
            "answerer": answerer.label,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "latency_ms": latency_ms,
        }
        message_id, created_at = uuid7(), datetime.now(UTC)
        if conversation is not None:
            stored = await self.conversations.add_message(
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    citations=citations,
                    sources=sources_public,
                    usage=usage_payload,
                )
            )
            message_id, created_at = stored.id, stored.created_at
        await UsageRepository(self.session).add(
            UsageEvent(
                workspace_id=workspace.id,
                user_id=principal.user_id,
                api_key_id=principal.api_key_id,
                kind=UsageKind.ASK,
                engine=answerer.label,
                latency_ms=latency_ms,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
        )
        await self.session.commit()
        metrics.ANSWERS.labels(answerer.label.split(":")[0]).inc()
        metrics.MODEL_TOKENS.labels("prompt").inc(usage.prompt_tokens)
        metrics.MODEL_TOKENS.labels("completion").inc(usage.completion_tokens)
        yield AskEvent(
            "done",
            {
                "conversation_id": str(conversation.id) if conversation else None,
                "message": {
                    "id": str(message_id),
                    "role": MessageRole.ASSISTANT.value,
                    "content": answer,
                    "citations": citations,
                    "sources": sources_public,
                    "usage": usage_payload,
                    "created_at": (created_at or datetime.now(UTC)).isoformat(),
                },
            },
        )
