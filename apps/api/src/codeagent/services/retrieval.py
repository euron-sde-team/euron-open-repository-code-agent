"""Retrieval over the code index, shared by search, answers and the agent.

question -> named symbols (exact) + vector chunks + keyword chunks -> rank fusion
         -> at most two sources per file -> numbered sources + reference-graph facts
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.ai.retrieval import cap_per_group, reciprocal_rank_fusion
from codeagent.ai.sources import CodeSource, Location, SymbolFacts
from codeagent.codeintel.terms import identifiers, unique_terms
from codeagent.core import metrics
from codeagent.repositories.index import EdgeRow, IndexRepository, SymbolRow
from codeagent.repositories.repos import ReposRepository, SearchScope
from codeagent.repositories.search import ChunkRow, SearchRepository
from codeagent.services.container import Container

MAX_DEFINITION_LINES = 60


def keyword_query(text: str) -> str | None:
    """An OR query over the text's search terms; `simple` config, terms already stemmed."""
    words = [w for w in unique_terms(text, 24) if w.isalnum()]
    return " | ".join(words) or None


@dataclass(slots=True)
class Retrieved:
    sources: list[CodeSource]
    facts: list[SymbolFacts]
    focus: list[uuid.UUID]


def short_name(qualified: str) -> str:
    """`pkg.mod.Invoice.tax` as `Invoice.tax`, `pkg.mod.calc_tax` as `calc_tax`."""
    parts = qualified.split(".")
    if len(parts) >= 2 and parts[-2][:1].isupper():
        return ".".join(parts[-2:])
    return parts[-1]


def _locations(edges: Sequence[EdgeRow]) -> list[Location]:
    """Edges as places, once per symbol and file (a test calling a function twice is one test)."""
    seen: set[tuple[str, str]] = set()
    found: list[Location] = []
    for edge in edges:
        name = short_name(edge.name)
        if (name, edge.path) not in seen:
            seen.add((name, edge.path))
            found.append(Location(name, edge.path, edge.line))
    return found


class RetrievalService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.search = SearchRepository(session)
        self.index = IndexRepository(session)
        self.repos = ReposRepository(session)

    async def scopes(
        self, workspace_id: uuid.UUID, repository_ids: Sequence[uuid.UUID] | None = None
    ) -> list[SearchScope]:
        return await self.repos.scopes(workspace_id, repository_ids)

    def _source(self, row: ChunkRow, scope: SearchScope, score: float) -> CodeSource:
        return CodeSource(
            repository_id=scope.repository_id,
            repository=scope.slug,
            file_id=row.file_id,
            path=row.path,
            language=row.language,
            start_line=row.start_line,
            end_line=row.end_line,
            text=row.content,
            chunk_id=row.id,
            symbol_id=row.symbol_id,
            symbol_name=row.symbol_name,
            symbol_kind=row.kind,
            qualified_name=row.qualified_name,
            signature=row.signature,
            doc=row.doc,
            is_test=row.is_test,
            score=score,
        )

    async def chunks(
        self,
        workspace_id: uuid.UUID,
        scopes: list[SearchScope],
        query: str,
        *,
        limit: int,
        vector: np.ndarray | None = None,
    ) -> tuple[list[CodeSource], dict[uuid.UUID, tuple[float | None, float | None]]]:
        """Fused vector and keyword candidates, best first, with their two raw scores."""
        if not scopes:
            return [], {}
        started = time.perf_counter()
        snapshot_ids = [scope.snapshot_id for scope in scopes]
        by_snapshot = {scope.snapshot_id: scope for scope in scopes}
        query_vector = vector if vector is not None else await self.c.embedder.embed_query(query)
        candidates = max(limit * 3, 30)
        by_vector = await self.search.vector_candidates(snapshot_ids, query_vector, candidates)
        by_keyword = await self.search.keyword_candidates(
            snapshot_ids, keyword_query(query), candidates
        )
        fused = reciprocal_rank_fusion([i for i, _ in by_vector], [i for i, _ in by_keyword])
        ranked = sorted(fused, key=lambda item: fused[item], reverse=True)[:candidates]
        rows = await self.search.hydrate(workspace_id, ranked)
        vector_scores, keyword_scores = dict(by_vector), dict(by_keyword)
        sources = [
            self._source(row, by_snapshot[row.snapshot_id], fused[chunk_id])
            for chunk_id in ranked
            if (row := rows.get(chunk_id)) is not None and row.snapshot_id in by_snapshot
        ]
        metrics.SEARCH_DURATION.labels("semantic").observe(time.perf_counter() - started)
        scores = {cid: (vector_scores.get(cid), keyword_scores.get(cid)) for cid in ranked}
        return sources[:limit], scores

    async def _definition(
        self, workspace_id: uuid.UUID, symbol: SymbolRow, scope: SearchScope
    ) -> CodeSource | None:
        file = await self.index.file(workspace_id, symbol.file_id)
        if file is None or file.content is None:
            return None
        lines = file.content.split("\n")
        end = min(symbol.end_line, symbol.start_line + MAX_DEFINITION_LINES - 1)
        return CodeSource(
            repository_id=scope.repository_id,
            repository=scope.slug,
            file_id=symbol.file_id,
            path=symbol.path,
            language=symbol.language,
            start_line=symbol.start_line,
            end_line=end,
            text="\n".join(lines[symbol.start_line - 1 : end]),
            symbol_id=symbol.id,
            symbol_name=symbol.name,
            symbol_kind=symbol.kind,
            qualified_name=symbol.qualified_name,
            signature=symbol.signature,
            doc=symbol.doc,
            is_test=symbol.is_test,
            score=1.0,
        )

    async def facts(self, symbols: Sequence[SymbolRow]) -> list[SymbolFacts]:
        result = []
        for symbol in symbols:
            incoming = await self.index.incoming(symbol.id, limit=60)
            outgoing = await self.index.outgoing(symbol.id, limit=30)
            result.append(
                SymbolFacts(
                    symbol_id=symbol.id,
                    name=symbol.name,
                    qualified_name=symbol.qualified_name,
                    kind=symbol.kind,
                    path=symbol.path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    signature=symbol.signature,
                    doc=symbol.doc,
                    callers=_locations(
                        [e for e in incoming if e.kind in {"call", "inherit"} and not e.is_test]
                    ),
                    callees=_locations([e for e in outgoing if not e.is_test]),
                    tests=_locations(
                        [e for e in incoming if e.kind in {"call", "inherit"} and e.is_test]
                    ),
                )
            )
        return result

    async def for_question(
        self, workspace_id: uuid.UUID, scopes: list[SearchScope], question: str, *, limit: int
    ) -> Retrieved:
        if not scopes:
            return Retrieved([], [], [])
        by_snapshot = {scope.snapshot_id: scope for scope in scopes}
        names = identifiers(question)
        wanted = list(dict.fromkeys([*names, *(name.rsplit(".", 1)[-1] for name in names)]))
        named = (
            await self.index.symbols_named(list(by_snapshot), wanted, limit=12) if wanted else []
        )
        # `Invoice.total`: prefer the method of that class over other `total`s.
        owners = {name.rsplit(".", 2)[-2] for name in names if "." in name}
        if owners:
            named.sort(key=lambda s: s.parent_name not in owners)
        named = [s for s in named if not s.is_test] or named
        definitions: list[CodeSource] = []
        for symbol in named[:3]:
            scope = by_snapshot.get(symbol.snapshot_id)
            if scope is not None:
                source = await self._definition(workspace_id, symbol, scope)
                if source is not None:
                    definitions.append(source)
        chunks, _ = await self.chunks(workspace_id, scopes, question, limit=limit * 2)
        merged: list[CodeSource] = list(definitions)
        for source in chunks:
            overlaps = any(
                s.path == source.path
                and s.start_line <= source.end_line
                and source.start_line <= s.end_line
                for s in merged
            )
            if not overlaps:
                merged.append(source)
        sources = cap_per_group(merged, lambda s: (s.repository, s.path), per_group=2, limit=limit)
        for number, source in enumerate(sources, start=1):
            source.n = number
        focus_rows = named[:3]
        extra_ids = [
            s.symbol_id
            for s in sources
            if s.symbol_id and s.symbol_id not in {r.id for r in focus_rows}
        ]
        extra = await self.index.symbols_by_id(extra_ids[:3])
        facts = await self.facts([*focus_rows, *extra])
        return Retrieved(sources, facts, [row.id for row in focus_rows])
