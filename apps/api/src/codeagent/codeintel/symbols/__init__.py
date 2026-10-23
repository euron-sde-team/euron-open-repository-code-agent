"""Symbol and reference extraction, one extractor per language family.

    outline = extract(language, source)

Python uses the standard library `ast`; JavaScript, TypeScript, TSX and Go use tree-sitter
grammars. An extractor never raises on bad input: a file that does not parse comes back
with no symbols and an `error` message, and indexing carries on.
"""

from __future__ import annotations

from codeagent.codeintel import languages
from codeagent.codeintel.symbols.types import FileOutline, ImportDraft, RefDraft, SymbolDraft

__all__ = ["FileOutline", "ImportDraft", "RefDraft", "SymbolDraft", "extract", "supports"]


def supports(language: str) -> bool:
    return language in languages.STRUCTURED


def extract(language: str, source: str, *, module: str = "") -> FileOutline:
    """Symbols, references and imports of one file. `module` prefixes qualified names."""
    if language == languages.PYTHON:
        from codeagent.codeintel.symbols.python import extract_python

        return extract_python(source, module=module)
    if language in {languages.JAVASCRIPT, languages.TYPESCRIPT, languages.TSX, languages.GO}:
        from codeagent.codeintel.symbols.treesitter import extract_treesitter

        return extract_treesitter(language, source, module=module)
    return FileOutline()
