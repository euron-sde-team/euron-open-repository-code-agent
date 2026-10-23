"""What an answerer is given: numbered code sources and facts from the reference graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

SNIPPET_LINES = 14


@dataclass(slots=True)
class CodeSource:
    """A range of lines from one file, numbered `n` for citation."""

    repository_id: uuid.UUID
    repository: str
    file_id: uuid.UUID
    path: str
    language: str
    start_line: int
    end_line: int
    text: str
    chunk_id: uuid.UUID | None = None
    symbol_id: uuid.UUID | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    qualified_name: str | None = None
    signature: str = ""
    doc: str = ""
    is_test: bool = False
    score: float = 0.0
    n: int = 0

    @property
    def label(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"

    def contains(self, path: str, line: int) -> bool:
        return self.path == path and self.start_line <= line <= self.end_line

    def snippet(self, lines: int = SNIPPET_LINES) -> str:
        return "\n".join(self.text.split("\n")[:lines])

    def public(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "repository_id": str(self.repository_id),
            "repository": self.repository,
            "file_id": str(self.file_id),
            "path": self.path,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.qualified_name or self.symbol_name,
            "symbol_kind": self.symbol_kind,
            "snippet": self.snippet(),
            "score": round(self.score, 4),
        }


@dataclass(frozen=True, slots=True)
class Location:
    name: str
    path: str
    line: int


@dataclass(slots=True)
class SymbolFacts:
    """A symbol and its neighbourhood in the reference graph."""

    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    callers: list[Location] = field(default_factory=list)
    callees: list[Location] = field(default_factory=list)
    tests: list[Location] = field(default_factory=list)
