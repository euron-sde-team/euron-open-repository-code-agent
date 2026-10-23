from __future__ import annotations

import uuid

from pydantic import Field

from codeagent.schemas.common import ApiModel


class SymbolHitOut(ApiModel):
    id: uuid.UUID
    repository: str
    name: str
    qualified_name: str
    kind: str
    path: str
    language: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    ref_count: int
    is_test: bool


class SymbolSearchOut(ApiModel):
    query: str
    hits: list[SymbolHitOut]
    took_ms: int


class LineMatchOut(ApiModel):
    line: int
    text: str
    ranges: list[tuple[int, int]] = Field(description="[start, end) character ranges of the match.")


class FileMatchOut(ApiModel):
    repository: str
    path: str
    language: str
    matches: list[LineMatchOut]


class TextSearchOut(ApiModel):
    query: str
    regex: bool
    files: list[FileMatchOut]
    match_count: int
    truncated: bool
    took_ms: int


class SemanticHitOut(ApiModel):
    repository: str
    path: str
    language: str
    start_line: int
    end_line: int
    symbol: str | None
    kind: str | None
    snippet: str
    score: float
    vector_score: float | None
    keyword_score: float | None


class SemanticSearchOut(ApiModel):
    query: str
    hits: list[SemanticHitOut]
    took_ms: int
