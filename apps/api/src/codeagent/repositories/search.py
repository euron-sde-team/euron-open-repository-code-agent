"""The search queries: symbols, text and the two candidate lists behind semantic search.

Every statement is static SQL with bound parameters; nothing is assembled from user input.
Text search narrows files with the trigram index first and only then splits them into
lines inside Postgres, under a statement timeout, so a costly pattern is cut off rather
than allowed to run.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import text

from codeagent.repositories.base import Store

_SYMBOLS = text(
    "SELECT s.id, s.snapshot_id, s.name, s.qualified_name, s.kind, s.start_line, s.end_line, "
    "s.signature, s.doc, s.ref_count, f.id AS file_id, f.path, f.language, f.is_test, "
    "similarity(lower(s.name), :q) AS sim "
    "FROM symbols s JOIN repo_files f ON f.id = s.file_id "
    "WHERE s.snapshot_id = ANY(:snapshots) "
    "AND (CAST(:kind AS text) IS NULL OR s.kind = :kind) "
    "AND (lower(s.name) LIKE :prefix ESCAPE '\\' OR lower(s.name) % :q "
    "OR lower(s.qualified_name) LIKE :contains ESCAPE '\\') "
    "ORDER BY (lower(s.name) = :q) DESC, (lower(s.name) LIKE :prefix ESCAPE '\\') DESC, "
    "f.is_test, sim DESC, s.ref_count DESC, f.path "
    "LIMIT :limit"
)

_TEXT_TEMPLATE = (
    "WITH candidates AS ("
    " SELECT f.id, f.snapshot_id, f.path, f.language, f.content FROM repo_files f"
    " WHERE f.snapshot_id = ANY(:snapshots) AND f.content IS NOT NULL"
    " AND (CAST(:language AS text) IS NULL OR f.language = :language)"
    " AND (CAST(:path_like AS text) IS NULL OR f.path LIKE :path_like ESCAPE '\\')"
    " AND {file_match}"
    " ORDER BY f.path LIMIT :max_files"
    ") "
    "SELECT file_id, snapshot_id, path, language, line_no, line_text FROM ("
    " SELECT c.id AS file_id, c.snapshot_id, c.path, c.language, l.n AS line_no,"
    " left(l.line, 500) AS line_text,"
    " row_number() OVER (PARTITION BY c.id ORDER BY l.n) AS rank_in_file"
    " FROM candidates c"
    " CROSS JOIN LATERAL regexp_split_to_table(c.content, E'\\n') WITH ORDINALITY AS l(line, n)"
    " WHERE {line_match}"
    ") hits WHERE rank_in_file <= :per_file ORDER BY path, line_no LIMIT :max_lines"
)
# One static statement per mode: the operator differs, the inputs are always bound.
_TEXT = {
    "literal": text(
        _TEXT_TEMPLATE.format(
            file_match="f.content ILIKE :like ESCAPE '\\'",
            line_match="strpos(lower(l.line), lower(:needle)) > 0",
        )
    ),
    "literal_cs": text(
        _TEXT_TEMPLATE.format(
            file_match="f.content LIKE :like ESCAPE '\\'",
            line_match="strpos(l.line, :needle) > 0",
        )
    ),
    "regex": text(
        _TEXT_TEMPLATE.format(file_match="f.content ~* :needle", line_match="l.line ~* :needle")
    ),
    "regex_cs": text(
        _TEXT_TEMPLATE.format(file_match="f.content ~ :needle", line_match="l.line ~ :needle")
    ),
}
_TIMEOUT = text("SELECT set_config('statement_timeout', :ms, true)")
_TUNE_HNSW = text(
    "SELECT set_config('hnsw.ef_search', :ef_search, true), "
    "set_config('hnsw.iterative_scan', 'relaxed_order', true)"
)
_VECTOR = text(
    "SELECT c.id, 1 - (c.embedding <=> :query) AS score FROM code_chunks c "
    "WHERE c.snapshot_id = ANY(:snapshots) "
    "ORDER BY c.embedding <=> :query LIMIT :limit"
)
_KEYWORD = text(
    "SELECT c.id, ts_rank_cd(c.tsv, q, 32) AS rank "
    "FROM code_chunks c, to_tsquery('simple', :query) q "
    "WHERE c.snapshot_id = ANY(:snapshots) AND c.tsv @@ q "
    "ORDER BY rank DESC LIMIT :limit"
)
_HYDRATE = text(
    "SELECT c.id, c.snapshot_id, c.file_id, c.symbol_id, c.start_line, c.end_line, c.content, "
    "f.path, f.language, f.is_test, s.name AS symbol_name, s.qualified_name, s.kind, "
    "s.signature, s.doc "
    "FROM code_chunks c JOIN repo_files f ON f.id = c.file_id "
    "LEFT JOIN symbols s ON s.id = c.symbol_id "
    "WHERE c.workspace_id = :workspace_id AND c.id = ANY(:ids)"
)


@dataclass(frozen=True, slots=True)
class SymbolHit:
    id: uuid.UUID
    snapshot_id: uuid.UUID
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    ref_count: int
    file_id: uuid.UUID
    path: str
    language: str
    is_test: bool
    similarity: float


@dataclass(frozen=True, slots=True)
class LineHit:
    file_id: uuid.UUID
    snapshot_id: uuid.UUID
    path: str
    language: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class ChunkRow:
    id: uuid.UUID
    snapshot_id: uuid.UUID
    file_id: uuid.UUID
    symbol_id: uuid.UUID | None
    start_line: int
    end_line: int
    content: str
    path: str
    language: str
    is_test: bool
    symbol_name: str | None
    qualified_name: str | None
    kind: str | None
    signature: str
    doc: str


def like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SearchRepository(Store):
    async def symbols(
        self, snapshot_ids: Sequence[uuid.UUID], query: str, kind: str | None, limit: int
    ) -> list[SymbolHit]:
        q = query.strip().lower()
        rows = await self.session.execute(
            _SYMBOLS,
            {
                "snapshots": list(snapshot_ids),
                "q": q,
                "kind": kind,
                "prefix": f"{like_escape(q)}%",
                "contains": f"%{like_escape(q)}%",
                "limit": limit,
            },
        )
        return [
            SymbolHit(
                id=r.id,
                snapshot_id=r.snapshot_id,
                name=r.name,
                qualified_name=r.qualified_name,
                kind=r.kind,
                start_line=r.start_line,
                end_line=r.end_line,
                signature=r.signature,
                doc=r.doc,
                ref_count=r.ref_count,
                file_id=r.file_id,
                path=r.path,
                language=r.language,
                is_test=r.is_test,
                similarity=float(r.sim or 0),
            )
            for r in rows.all()
        ]

    async def text(
        self,
        snapshot_ids: Sequence[uuid.UUID],
        needle: str,
        *,
        regex: bool,
        case_sensitive: bool,
        language: str | None,
        path_like: str | None,
        timeout_ms: int,
        max_files: int = 200,
        per_file: int = 20,
        max_lines: int = 200,
    ) -> list[LineHit]:
        mode = ("regex" if regex else "literal") + ("_cs" if case_sensitive else "")
        await self.session.execute(_TIMEOUT, {"ms": str(timeout_ms)})
        params: dict[str, Any] = {
            "snapshots": list(snapshot_ids),
            "language": language,
            "path_like": path_like,
            "needle": needle,
            "like": f"%{like_escape(needle)}%",
            "max_files": max_files,
            "per_file": per_file,
            "max_lines": max_lines,
        }
        rows = await self.session.execute(_TEXT[mode], params)
        return [LineHit(*row) for row in rows.all()]

    async def vector_candidates(
        self, snapshot_ids: Sequence[uuid.UUID], query: np.ndarray, limit: int
    ) -> list[tuple[uuid.UUID, float]]:
        await self.session.execute(_TUNE_HNSW, {"ef_search": str(max(40, limit * 2))})
        rows = (
            await self.session.execute(
                _VECTOR, {"query": query, "snapshots": list(snapshot_ids), "limit": limit}
            )
        ).all()
        # relaxed_order may return near-ties out of order; rank fusion needs the true order.
        return sorted(((r.id, float(r.score)) for r in rows), key=lambda item: -item[1])

    async def keyword_candidates(
        self, snapshot_ids: Sequence[uuid.UUID], tsquery: str | None, limit: int
    ) -> list[tuple[uuid.UUID, float]]:
        if not tsquery:
            return []
        rows = (
            await self.session.execute(
                _KEYWORD, {"query": tsquery, "snapshots": list(snapshot_ids), "limit": limit}
            )
        ).all()
        return [(r.id, float(r.rank)) for r in rows]

    async def hydrate(
        self, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ChunkRow]:
        if not ids:
            return {}
        rows = (
            await self.session.execute(_HYDRATE, {"workspace_id": workspace_id, "ids": list(ids)})
        ).all()
        return {
            r.id: ChunkRow(
                id=r.id,
                snapshot_id=r.snapshot_id,
                file_id=r.file_id,
                symbol_id=r.symbol_id,
                start_line=r.start_line,
                end_line=r.end_line,
                content=r.content,
                path=r.path,
                language=r.language,
                is_test=r.is_test,
                symbol_name=r.symbol_name,
                qualified_name=r.qualified_name,
                kind=r.kind,
                signature=r.signature or "",
                doc=r.doc or "",
            )
            for r in rows
        }
