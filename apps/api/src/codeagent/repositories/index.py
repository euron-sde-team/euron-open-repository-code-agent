"""The code index of a snapshot: bulk writes from the indexer, reads for the code view,
the reference graph, answers and the agent."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import aliased

from codeagent.models import CodeChunk, RepoFile, Symbol, SymbolRef
from codeagent.repositories.base import Store

BATCH = 1000


@dataclass(frozen=True, slots=True)
class FileEntry:
    id: uuid.UUID
    path: str
    language: str
    size_bytes: int
    line_count: int
    is_test: bool
    symbol_count: int
    indexed: bool


@dataclass(frozen=True, slots=True)
class SymbolRow:
    id: uuid.UUID
    name: str
    qualified_name: str
    kind: str
    path: str
    file_id: uuid.UUID
    language: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    ref_count: int
    parent_name: str | None
    is_test: bool


@dataclass(frozen=True, slots=True)
class EdgeRow:
    """One side of a reference: the symbol (or file) at the other end, and where it happens."""

    symbol_id: uuid.UUID | None
    name: str
    kind: str
    path: str
    line: int
    is_test: bool


def _symbol_row(
    symbol: Symbol, path: str, language: str, parent: str | None, is_test: bool
) -> SymbolRow:
    return SymbolRow(
        id=symbol.id,
        name=symbol.name,
        qualified_name=symbol.qualified_name,
        kind=symbol.kind,
        path=path,
        file_id=symbol.file_id,
        language=language,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        signature=symbol.signature,
        doc=symbol.doc,
        ref_count=symbol.ref_count,
        parent_name=parent,
        is_test=is_test,
    )


class IndexRepository(Store):
    async def clear(self, snapshot_id: uuid.UUID) -> None:
        """Remove a snapshot's index (symbols, references and chunks cascade from files)."""
        await self.session.execute(delete(RepoFile).where(RepoFile.snapshot_id == snapshot_id))

    async def _bulk(self, model: type[Any], rows: Sequence[dict[str, Any]]) -> None:
        for start in range(0, len(rows), BATCH):
            await self.session.execute(insert(model), list(rows[start : start + BATCH]))

    async def write(
        self,
        files: Sequence[dict[str, Any]],
        symbols: Sequence[dict[str, Any]],
        refs: Sequence[dict[str, Any]],
        chunks: Sequence[dict[str, Any]],
    ) -> None:
        """Insert a whole index. Symbols must come parents first (the caller sorts them)."""
        await self._bulk(RepoFile, files)
        await self._bulk(Symbol, symbols)
        await self._bulk(SymbolRef, refs)
        await self._bulk(CodeChunk, chunks)

    async def files(self, snapshot_id: uuid.UUID) -> list[FileEntry]:
        result = await self.session.execute(
            select(
                RepoFile.id,
                RepoFile.path,
                RepoFile.language,
                RepoFile.size_bytes,
                RepoFile.line_count,
                RepoFile.is_test,
                RepoFile.symbol_count,
                RepoFile.content.is_not(None).label("indexed"),
            )
            .where(RepoFile.snapshot_id == snapshot_id)
            .order_by(RepoFile.path)
        )
        return [FileEntry(*row) for row in result.all()]

    async def file_by_path(self, snapshot_id: uuid.UUID, path: str) -> RepoFile | None:
        result = await self.session.execute(
            select(RepoFile).where(RepoFile.snapshot_id == snapshot_id, RepoFile.path == path)
        )
        return result.scalar_one_or_none()

    async def file(self, workspace_id: uuid.UUID, file_id: uuid.UUID) -> RepoFile | None:
        result = await self.session.execute(
            select(RepoFile).where(RepoFile.id == file_id, RepoFile.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def symbols_in_file(self, file_id: uuid.UUID) -> list[Symbol]:
        result = await self.session.execute(
            select(Symbol)
            .where(Symbol.file_id == file_id)
            .order_by(Symbol.start_line, Symbol.end_line.desc())
        )
        return list(result.scalars())

    async def symbol(self, workspace_id: uuid.UUID, symbol_id: uuid.UUID) -> SymbolRow | None:
        parent = aliased(Symbol)
        row = (
            await self.session.execute(
                select(Symbol, RepoFile.path, RepoFile.language, parent.name, RepoFile.is_test)
                .join(RepoFile, RepoFile.id == Symbol.file_id)
                .outerjoin(parent, parent.id == Symbol.parent_id)
                .where(Symbol.id == symbol_id, Symbol.workspace_id == workspace_id)
            )
        ).first()
        return _symbol_row(*row) if row else None

    async def symbols_named(
        self, snapshot_ids: Sequence[uuid.UUID], names: Sequence[str], *, limit: int = 50
    ) -> list[SymbolRow]:
        if not names or not snapshot_ids:
            return []
        parent = aliased(Symbol)
        result = await self.session.execute(
            select(Symbol, RepoFile.path, RepoFile.language, parent.name, RepoFile.is_test)
            .join(RepoFile, RepoFile.id == Symbol.file_id)
            .outerjoin(parent, parent.id == Symbol.parent_id)
            .where(Symbol.snapshot_id.in_(list(snapshot_ids)), Symbol.name.in_(list(names)))
            .order_by(RepoFile.is_test, Symbol.ref_count.desc(), RepoFile.path)
            .limit(limit)
        )
        return [_symbol_row(*row) for row in result.all()]

    async def symbols_by_id(self, symbol_ids: Sequence[uuid.UUID]) -> list[SymbolRow]:
        if not symbol_ids:
            return []
        parent = aliased(Symbol)
        result = await self.session.execute(
            select(Symbol, RepoFile.path, RepoFile.language, parent.name, RepoFile.is_test)
            .join(RepoFile, RepoFile.id == Symbol.file_id)
            .outerjoin(parent, parent.id == Symbol.parent_id)
            .where(Symbol.id.in_(list(symbol_ids)))
        )
        return [_symbol_row(*row) for row in result.all()]

    async def incoming(self, symbol_id: uuid.UUID, *, limit: int = 200) -> list[EdgeRow]:
        """References to a symbol: who calls, imports or extends it, and where."""
        source = aliased(Symbol)
        result = await self.session.execute(
            select(
                SymbolRef.source_symbol_id,
                source.qualified_name,
                SymbolRef.kind,
                RepoFile.path,
                SymbolRef.line,
                RepoFile.is_test,
            )
            .join(RepoFile, RepoFile.id == SymbolRef.file_id)
            .outerjoin(source, source.id == SymbolRef.source_symbol_id)
            .where(SymbolRef.target_symbol_id == symbol_id)
            .order_by(RepoFile.is_test, RepoFile.path, SymbolRef.line)
            .limit(limit)
        )
        return [
            EdgeRow(sid, name or path.rsplit("/", 1)[-1], kind, path, line, is_test)
            for sid, name, kind, path, line, is_test in result.all()
        ]

    async def outgoing(self, symbol_id: uuid.UUID, *, limit: int = 200) -> list[EdgeRow]:
        """What a symbol calls or extends, resolved to definitions where the index could."""
        target = aliased(Symbol)
        target_file = aliased(RepoFile)
        result = await self.session.execute(
            select(
                SymbolRef.target_symbol_id,
                target.qualified_name,
                SymbolRef.target_name,
                SymbolRef.kind,
                target_file.path,
                target.start_line,
                target_file.is_test,
            )
            .join(target, target.id == SymbolRef.target_symbol_id)
            .join(target_file, target_file.id == target.file_id)
            .where(SymbolRef.source_symbol_id == symbol_id)
            .order_by(SymbolRef.line)
            .limit(limit)
        )
        seen: set[uuid.UUID] = set()
        edges = []
        for tid, qualified, name, kind, path, line, is_test in result.all():
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            edges.append(EdgeRow(tid, qualified or name, kind, path, line, is_test))
        return edges
