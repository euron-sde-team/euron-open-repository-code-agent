"""Conversations and cited answers, as JSON or as server-sent events."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

import orjson
from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from codeagent.api.deps import Access, AccessDep, AskLimit, ContainerDep, SessionDep
from codeagent.api.presenters import conversation_out, message_out
from codeagent.core.errors import InternalError
from codeagent.schemas.chat import (
    AnswerOut,
    AskRequest,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from codeagent.services.ask import AskEvent, AskService
from codeagent.services.container import Container

router = APIRouter(tags=["ask"])


def _frame(event: AskEvent) -> bytes:
    return b"event: " + event.event.encode() + b"\ndata: " + orjson.dumps(event.data) + b"\n\n"


async def _answer(events: AsyncIterator[AskEvent]) -> AnswerOut:
    async with aclosing(events):  # type: ignore[type-var]
        async for event in events:
            if event.event == "error" and event.error is not None:
                raise event.error
            if event.event == "done":
                return AnswerOut.model_validate(event.data)
    raise InternalError("The answer did not complete.")


def _stream(
    request: Request,
    container: Container,
    access: Access,
    question: str,
    *,
    conversation_id: uuid.UUID | None,
    repository_ref: str | None,
) -> StreamingResponse:
    async def body() -> AsyncIterator[bytes]:
        # Its own session: the request-scoped one is not safe to share with a long stream.
        # Access and existence were already checked by the route, before the 200 went out.
        async with container.db.session() as session:
            service = AskService(container, session)
            conversation = (
                await service.get_conversation(
                    access.workspace.id, conversation_id, access.principal
                )
                if conversation_id
                else None
            )
            repository = (
                await service.resolve_repository(access.workspace.id, repository_ref)
                if conversation is None
                else None
            )
            events = service.ask(
                access.workspace,
                access.principal,
                question,
                conversation=conversation,
                repository=repository,
            )
            async with aclosing(events):
                async for event in events:
                    if await request.is_disconnected():
                        return
                    yield _frame(event)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"cache-control": "no-store", "x-accel-buffering": "no"},
    )


@router.post(
    "/workspaces/{workspace}/ask",
    summary="Ask about the code (no conversation is kept)",
    dependencies=[AskLimit],
)
async def ask(
    body: AskRequest, access: AccessDep, container: ContainerDep, session: SessionDep
) -> AnswerOut:
    service = AskService(container, session)
    repository = await service.resolve_repository(access.workspace.id, body.repository)
    return await _answer(
        service.ask(access.workspace, access.principal, body.question, repository=repository)
    )


@router.post(
    "/workspaces/{workspace}/ask/stream",
    summary="Ask about the code, streamed as server-sent events",
    dependencies=[AskLimit],
)
async def ask_stream(
    body: AskRequest,
    request: Request,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> StreamingResponse:
    await AskService(container, session).resolve_repository(access.workspace.id, body.repository)
    return _stream(
        request,
        container,
        access,
        body.question,
        conversation_id=None,
        repository_ref=body.repository,
    )


@router.get("/workspaces/{workspace}/conversations", summary="Your conversations, newest first")
async def list_conversations(
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationOut]:
    rows = await AskService(container, session).list_conversations(
        access.workspace.id, access.principal, limit=limit, offset=offset
    )
    return [conversation_out(c) for c in rows]


@router.post(
    "/workspaces/{workspace}/conversations",
    summary="Start a conversation",
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreate, access: AccessDep, container: ContainerDep, session: SessionDep
) -> ConversationOut:
    conversation = await AskService(container, session).create_conversation(
        access.workspace, access.principal, body.title, body.repository
    )
    return conversation_out(conversation)


@router.get("/workspaces/{workspace}/conversations/{conversation_id}", summary="A conversation")
async def get_conversation(
    conversation_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> ConversationOut:
    conversation = await AskService(container, session).get_conversation(
        access.workspace.id, conversation_id, access.principal
    )
    return conversation_out(conversation)


@router.patch("/workspaces/{workspace}/conversations/{conversation_id}", summary="Rename")
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> ConversationOut:
    service = AskService(container, session)
    conversation = await service.get_conversation(
        access.workspace.id, conversation_id, access.principal
    )
    return conversation_out(await service.rename(conversation, body.title))


@router.delete(
    "/workspaces/{workspace}/conversations/{conversation_id}",
    summary="Delete a conversation",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> None:
    service = AskService(container, session)
    await service.delete(
        await service.get_conversation(access.workspace.id, conversation_id, access.principal)
    )


@router.get(
    "/workspaces/{workspace}/conversations/{conversation_id}/messages",
    summary="The messages of a conversation, oldest first",
)
async def list_messages(
    conversation_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> list[MessageOut]:
    service = AskService(container, session)
    conversation = await service.get_conversation(
        access.workspace.id, conversation_id, access.principal
    )
    return [message_out(m) for m in await service.messages(conversation)]


@router.post(
    "/workspaces/{workspace}/conversations/{conversation_id}/messages",
    summary="Ask a follow-up in a conversation",
    dependencies=[AskLimit],
)
async def post_message(
    conversation_id: uuid.UUID,
    body: AskRequest,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> AnswerOut:
    service = AskService(container, session)
    conversation = await service.get_conversation(
        access.workspace.id, conversation_id, access.principal
    )
    return await _answer(
        service.ask(access.workspace, access.principal, body.question, conversation=conversation)
    )


@router.post(
    "/workspaces/{workspace}/conversations/{conversation_id}/messages/stream",
    summary="Ask a follow-up, streamed as server-sent events",
    dependencies=[AskLimit],
)
async def post_message_stream(
    conversation_id: uuid.UUID,
    body: AskRequest,
    request: Request,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> StreamingResponse:
    await AskService(container, session).get_conversation(
        access.workspace.id, conversation_id, access.principal
    )
    return _stream(
        request,
        container,
        access,
        body.question,
        conversation_id=conversation_id,
        repository_ref=None,
    )
