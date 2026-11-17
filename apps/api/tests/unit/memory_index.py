"""An in-memory SymbolIndex built from an IndexBuild, so planners run without a database."""

from __future__ import annotations

import uuid
from pathlib import Path

from codeagent.agent.types import FileInfo, RefInfo, RepoView, SymbolInfo
from codeagent.codeintel.builder import IndexBuild


class MemoryIndex:
    def __init__(self, build: IndexBuild) -> None:
        self.build = build
        self.paths = {f.id: f.path for f in build.files}
        self.symbols = {s.id: s for s in build.symbols}

    def _info(self, symbol_id: uuid.UUID) -> SymbolInfo:
        s = self.symbols[symbol_id]
        parent = self.symbols.get(s.parent_id) if s.parent_id else None
        return SymbolInfo(
            id=s.id,
            name=s.name,
            qualified_name=s.qualified_name,
            kind=s.kind,
            path=self.paths[s.file_id],
            start_line=s.start_line,
            end_line=s.end_line,
            parent_name=parent.name if parent else None,
        )

    async def by_name(self, name: str) -> list[SymbolInfo]:
        return [self._info(s.id) for s in self.build.symbols if s.name == name]

    async def refs_to(self, symbol_id: uuid.UUID) -> list[RefInfo]:
        return [
            RefInfo(
                self.paths[r.file_id],
                r.line,
                r.kind,
                self.symbols[r.source_symbol_id].name if r.source_symbol_id else None,
            )
            for r in self.build.refs
            if r.target_symbol_id == symbol_id
        ]

    async def callees_of(self, symbol_id: uuid.UUID) -> list[SymbolInfo]:
        return [
            self._info(r.target_symbol_id)
            for r in self.build.refs
            if r.source_symbol_id == symbol_id and r.target_symbol_id
        ]


def view_of(root: Path, build: IndexBuild) -> RepoView:
    return RepoView(
        root=root,
        files={f.path: FileInfo(f.path, f.language, f.is_test) for f in build.files},
        index=MemoryIndex(build),
    )
