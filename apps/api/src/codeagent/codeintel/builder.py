"""Build the whole index of one snapshot in memory: files, symbols, references, chunks.

Pure computation over file contents (no database, no network), so it is tested directly
and runs in a worker thread. Ids are generated here (UUIDv7), which lets symbols point at
their parents and references at their targets before anything is inserted.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from codeagent.codeintel import languages, symbols
from codeagent.codeintel.chunker import chunk_file
from codeagent.codeintel.resolve import FileNode, Resolver, SymbolNode
from codeagent.codeintel.symbols.python import module_name
from codeagent.codeintel.symbols.treesitter import script_module
from codeagent.codeintel.symbols.types import FileOutline, SymbolDraft
from codeagent.codeintel.terms import terms
from codeagent.core.ids import uuid7


@dataclass(slots=True)
class BuiltFile:
    id: uuid.UUID
    path: str
    language: str
    size_bytes: int
    line_count: int
    sha256: str
    is_test: bool
    content: str | None
    symbol_count: int = 0
    parse_error: str | None = None


@dataclass(slots=True)
class BuiltSymbol:
    id: uuid.UUID
    file_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    exported: bool
    depth: int
    ref_count: int = 0


@dataclass(slots=True)
class BuiltRef:
    id: uuid.UUID
    file_id: uuid.UUID
    source_symbol_id: uuid.UUID | None
    target_symbol_id: uuid.UUID | None
    target_name: str
    qualifier: str | None
    kind: str
    line: int


@dataclass(slots=True)
class BuiltChunk:
    id: uuid.UUID
    file_id: uuid.UUID
    symbol_id: uuid.UUID | None
    start_line: int
    end_line: int
    content: str
    terms: str
    embed_text: str
    token_count: int


@dataclass(slots=True)
class IndexBuild:
    files: list[BuiltFile] = field(default_factory=list)
    symbols: list[BuiltSymbol] = field(default_factory=list)
    refs: list[BuiltRef] = field(default_factory=list)
    chunks: list[BuiltChunk] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def languages(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for file in self.files:
            if file.content is None:
                continue
            entry = stats.setdefault(file.language, {"files": 0, "lines": 0, "bytes": 0})
            entry["files"] += 1
            entry["lines"] += file.line_count
            entry["bytes"] += file.size_bytes
        return dict(sorted(stats.items(), key=lambda item: -item[1]["bytes"]))

    def stats(self) -> dict[str, int]:
        indexed = [f for f in self.files if f.content is not None]
        return {
            "files": len(self.files),
            "indexed_files": len(indexed),
            "symbols": len(self.symbols),
            "references": len(self.refs),
            "resolved_references": sum(1 for r in self.refs if r.target_symbol_id is not None),
            "chunks": len(self.chunks),
            "lines": sum(f.line_count for f in indexed),
            "bytes": sum(f.size_bytes for f in self.files),
            "test_files": sum(1 for f in indexed if f.is_test),
        }


def module_for(path: str, language: str) -> str:
    if language == languages.PYTHON:
        return module_name(path)
    if language == languages.GO:
        return str(PurePosixPath(path).parent).replace("/", ".").strip(".")
    if language in {languages.JAVASCRIPT, languages.TYPESCRIPT, languages.TSX}:
        return script_module(path)
    return ""


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _line_count(text: str | None) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _depths(drafts: list[SymbolDraft]) -> dict[int, int]:
    """Nesting depth of every symbol, following parent links in any order (Go links late)."""
    parents = {d.key: d.parent for d in drafts}
    depths: dict[int, int] = {}
    for key in parents:
        chain = 0
        current = parents.get(key)
        seen = {key}
        while current is not None and current not in seen:
            seen.add(current)
            chain += 1
            current = parents.get(current)
        depths[key] = chain
    return depths


def build_index(
    sources: list[tuple[str, bytes | None, int]],
    *,
    max_file_bytes: int,
    chunk_max_lines: int,
    max_chunks: int = 50_000,
) -> IndexBuild:
    build = IndexBuild()
    nodes: list[FileNode] = []
    graph: list[SymbolNode] = []
    outlines: list[FileOutline | None] = []
    for path, data, size in sorted(sources, key=lambda item: item[0]):
        too_large = data is None or size > max_file_bytes
        binary = data is not None and languages.looks_binary(data[:8192])
        text = None if binary or too_large or data is None else _decode(data)
        language = languages.detect_language(path, text[:200] if text else "")
        built = BuiltFile(
            id=uuid7(),
            path=path,
            language=language,
            size_bytes=size,
            line_count=_line_count(text),
            sha256=hashlib.sha256(data).hexdigest() if data is not None else "",
            is_test=languages.is_test_path(path),
            content=text,
        )
        if too_large and not binary:
            build.warnings.append(
                {"path": path, "message": "Larger than the per-file limit; not indexed."}
            )
        build.files.append(built)
        if text is None or not symbols.supports(language):
            nodes.append(FileNode(path, "", language))
            outlines.append(None)
            continue
        module = module_for(path, language)
        outline = symbols.extract(language, text, module=module)
        if outline.error:
            built.parse_error = outline.error
            build.warnings.append({"path": path, "message": outline.error})
        nodes.append(FileNode(path, module, language, outline.imports))
        outlines.append(outline)

    # Symbols, with ids, parents and depths.
    file_symbol_ids: list[dict[int, uuid.UUID]] = []
    for index, (built, parsed) in enumerate(zip(build.files, outlines, strict=True)):
        ids: dict[int, uuid.UUID] = {}
        if parsed is not None:
            for draft in parsed.symbols:
                ids[draft.key] = uuid7()
            depth = _depths(parsed.symbols)
            for draft in parsed.symbols:
                parent_id = ids.get(draft.parent) if draft.parent is not None else None
                build.symbols.append(
                    BuiltSymbol(
                        id=ids[draft.key],
                        file_id=built.id,
                        parent_id=parent_id,
                        name=draft.name[:300],
                        qualified_name=draft.qualified_name[:1000],
                        kind=draft.kind.value,
                        start_line=draft.start_line,
                        end_line=draft.end_line,
                        signature=draft.signature,
                        doc=draft.doc,
                        exported=draft.exported,
                        depth=depth[draft.key],
                    )
                )
                graph.append(SymbolNode(ids[draft.key], index, draft.name, draft.kind, parent_id))
            built.symbol_count = len(parsed.symbols)
        file_symbol_ids.append(ids)

    resolver = Resolver(nodes, graph)
    by_id = {node.id: node for node in graph}
    incoming: Counter[uuid.UUID] = Counter()
    for index, (built, parsed) in enumerate(zip(build.files, outlines, strict=True)):
        if parsed is None:
            continue
        ids = file_symbol_ids[index]
        for ref in parsed.refs:
            source_id = ids.get(ref.source) if ref.source is not None else None
            target = resolver.resolve(index, ref, by_id.get(source_id) if source_id else None)
            if target is not None:
                incoming[target] += 1
            build.refs.append(
                BuiltRef(
                    id=uuid7(),
                    file_id=built.id,
                    source_symbol_id=source_id,
                    target_symbol_id=target,
                    target_name=ref.target[:300],
                    qualifier=ref.qualifier[:300] if ref.qualifier else None,
                    kind=ref.kind.value,
                    line=ref.line,
                )
            )
    for symbol in build.symbols:
        symbol.ref_count = incoming.get(symbol.id, 0)
    # Parents before children, so the self-referencing foreign key holds row by row.
    build.symbols.sort(key=lambda s: s.depth)

    # Chunks.
    for index, (built, parsed) in enumerate(zip(build.files, outlines, strict=True)):
        if built.content is None or len(build.chunks) >= max_chunks:
            continue
        drafts = parsed.symbols if parsed is not None else []
        ids = file_symbol_ids[index]
        for chunk in chunk_file(built.path, built.content, drafts, max_lines=chunk_max_lines):
            symbol_id = ids.get(chunk.symbol_key) if chunk.symbol_key is not None else None
            words = terms(f"{built.path}\n{chunk.context}\n{chunk.text}")
            build.chunks.append(
                BuiltChunk(
                    id=uuid7(),
                    file_id=built.id,
                    symbol_id=symbol_id,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    content=chunk.text,
                    terms=" ".join(words[:2000]),
                    embed_text=f"{chunk.context}\n{chunk.text}",
                    token_count=(len(chunk.text) + 3) // 4,
                )
            )
    return build
