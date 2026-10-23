from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from codeagent.schemas.common import ApiModel


class ConversationCreate(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    repository: str | None = Field(
        default=None, description="Repository id or slug to scope answers to."
    )


class ConversationUpdate(ApiModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationOut(ApiModel):
    id: uuid.UUID
    title: str
    repository_id: uuid.UUID | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class AskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=2000)
    repository: str | None = Field(
        default=None, description="Repository id or slug; every ready repository when omitted."
    )


class SourceOut(ApiModel):
    n: int
    repository_id: uuid.UUID
    repository: str
    file_id: uuid.UUID
    path: str
    language: str
    start_line: int
    end_line: int
    symbol: str | None = None
    symbol_kind: str | None = None
    snippet: str
    score: float


class CitationOut(ApiModel):
    n: int
    repository_id: uuid.UUID
    repository: str
    file_id: uuid.UUID
    path: str
    start_line: int
    end_line: int
    symbol: str | None = None
    snippet: str


class UsageOut(ApiModel):
    answerer: str
    prompt_tokens: int = Field(description="Tokens a model received (0 for the local answerer).")
    completion_tokens: int
    latency_ms: int


class MessageOut(ApiModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[CitationOut] = []
    sources: list[SourceOut] = []
    usage: UsageOut | None = None
    created_at: datetime


class AnswerOut(ApiModel):
    conversation_id: uuid.UUID | None
    message: MessageOut
