"""Symbol-aware chunking: the unit of semantic and keyword retrieval.

A chunk is a contiguous range of lines. Each top-level definition (function, class,
interface, type) is one chunk when it fits in `max_lines`; a larger class is split into its
methods plus windows over what lies between them; a larger function into overlapping
windows. Code outside any definition (imports, constants, scripts) and files without
symbols are cut into windows. Containment is decided by line ranges, not by parent links,
so Go methods (declared outside their struct) are chunked on their own like functions.
"""

from __future__ import annotations

from dataclasses import dataclass

from codeagent.codeintel.symbols.types import SymbolDraft, SymbolKind

DEFAULT_OVERLAP = 10
_UNIT_KINDS = frozenset(
    {
        SymbolKind.CLASS,
        SymbolKind.FUNCTION,
        SymbolKind.METHOD,
        SymbolKind.INTERFACE,
        SymbolKind.TYPE,
        SymbolKind.ENUM,
        SymbolKind.STRUCT,
    }
)


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    start_line: int
    end_line: int
    symbol_key: int | None
    context: str
    text: str


def windows(start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    """Line windows covering [start, end], each at most `size` long, overlapping by `overlap`."""
    if end < start:
        return []
    step = max(1, size - overlap)
    spans: list[tuple[int, int]] = []
    first = start
    while True:
        last = min(first + size - 1, end)
        spans.append((first, last))
        if last >= end:
            return spans
        first += step


def _contains(outer: SymbolDraft, inner: SymbolDraft) -> bool:
    return (
        outer.key != inner.key
        and outer.start_line <= inner.start_line
        and inner.end_line <= outer.end_line
        and (outer.start_line, -outer.end_line) != (inner.start_line, -inner.end_line)
    )


def chunk_file(
    path: str,
    text: str,
    symbols: list[SymbolDraft],
    *,
    max_lines: int = 60,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ChunkDraft]:
    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return []
    overlap = min(overlap, max_lines // 3)
    units = sorted(
        (s for s in symbols if s.kind in _UNIT_KINDS and s.start_line <= total),
        key=lambda s: (s.start_line, -s.end_line),
    )
    top = [u for u in units if not any(_contains(other, u) for other in units)]
    chunks: list[ChunkDraft] = []
    covered = [False] * (total + 2)

    def emit(first: int, last: int, symbol: SymbolDraft | None) -> None:
        last = min(last, total)
        body = "\n".join(lines[first - 1 : last])
        if not body.strip():
            return
        context = f"{path} > {symbol.qualified_name}" if symbol else path
        chunks.append(ChunkDraft(first, last, symbol.key if symbol else None, context, body))

    def cover(first: int, last: int) -> None:
        for line in range(first, min(last, total) + 1):
            covered[line] = True

    def emit_symbol(symbol: SymbolDraft) -> None:
        first, last = symbol.start_line, min(symbol.end_line, total)
        if last - first + 1 <= max_lines:
            emit(first, last, symbol)
            return
        inner = sorted(
            (u for u in units if _contains(symbol, u) and u.kind == SymbolKind.METHOD),
            key=lambda s: s.start_line,
        )
        if not inner:
            for a, b in windows(first, last, max_lines, overlap):
                emit(a, b, symbol)
            return
        cursor = first
        for method in inner:
            if method.start_line < cursor:
                continue
            for a, b in windows(cursor, method.start_line - 1, max_lines, overlap):
                emit(a, b, symbol)
            emit_symbol(method)
            cursor = method.end_line + 1
        for a, b in windows(cursor, last, max_lines, overlap):
            emit(a, b, symbol)

    for symbol in top:
        emit_symbol(symbol)
        cover(symbol.start_line, symbol.end_line)

    run_start: int | None = None
    for line in range(1, total + 2):
        if line <= total and not covered[line]:
            if run_start is None:
                run_start = line
            continue
        if run_start is not None:
            for a, b in windows(run_start, line - 1, max_lines, overlap):
                emit(a, b, None)
            run_start = None
    return sorted(chunks, key=lambda c: (c.start_line, c.end_line))
