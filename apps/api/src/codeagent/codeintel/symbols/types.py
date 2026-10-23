"""The shapes every extractor produces, independent of language and of the database."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SymbolKind(StrEnum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    STRUCT = "struct"


class RefKind(StrEnum):
    CALL = "call"
    IMPORT = "import"
    INHERIT = "inherit"


@dataclass(slots=True)
class SymbolDraft:
    """A definition. `key` is its position in the file's list; `parent` points at another key."""

    key: int
    name: str
    qualified_name: str
    kind: SymbolKind
    start_line: int
    end_line: int
    signature: str = ""
    doc: str = ""
    parent: int | None = None
    exported: bool = True


@dataclass(slots=True)
class RefDraft:
    """A use of a name, `qualifier.target`, at `line` inside symbol `source` (None: top level)."""

    target: str
    kind: RefKind
    line: int
    source: int | None = None
    qualifier: str | None = None


@dataclass(slots=True)
class ImportDraft:
    """`alias` in this file stands for `name` from `module` (name None: the module itself)."""

    alias: str
    module: str
    name: str | None
    line: int


@dataclass(slots=True)
class FileOutline:
    symbols: list[SymbolDraft] = field(default_factory=list)
    refs: list[RefDraft] = field(default_factory=list)
    imports: list[ImportDraft] = field(default_factory=list)
    error: str | None = None


def first_paragraph(text: str, limit: int = 300) -> str:
    """The first paragraph of a docstring or comment, on one line, at most `limit` chars."""
    paragraph = text.strip().split("\n\n", 1)[0]
    flat = " ".join(paragraph.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3].rsplit(" ", 1)[0] + "..."


def one_line(text: str, limit: int = 200) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."
