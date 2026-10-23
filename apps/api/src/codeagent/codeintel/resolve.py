"""Turn references into edges of the reference graph: who calls, imports or extends what.

Resolution is static and conservative. A reference resolves to a definition only when the
evidence is good: a definition in the same file, a name the file imports, a method of the
enclosing class for `self.x()` and `this.x()`, a class named by the qualifier, or a name
defined exactly once in the whole snapshot. Anything ambiguous stays unresolved, because a
wrong edge in "who calls this?" is worse than a missing one.
"""

from __future__ import annotations

import posixpath
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from codeagent.codeintel import languages
from codeagent.codeintel.symbols.types import ImportDraft, RefDraft, RefKind, SymbolKind

_SELF = frozenset({"self", "cls", "this"})
_CLASSLIKE = frozenset({SymbolKind.CLASS, SymbolKind.STRUCT, SymbolKind.INTERFACE, SymbolKind.TYPE})


@dataclass(frozen=True, slots=True)
class SymbolNode:
    id: uuid.UUID
    file: int
    name: str
    kind: SymbolKind
    parent: uuid.UUID | None


@dataclass(slots=True)
class FileNode:
    path: str
    module: str
    language: str
    imports: list[ImportDraft] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Alias:
    module: str
    name: str | None  # None: the alias stands for the module itself


def python_import_module(file: FileNode, module: str) -> str:
    """Absolute module of a (possibly relative) Python import seen from `file`."""
    level = len(module) - len(module.lstrip("."))
    if level == 0:
        return module
    parts = file.module.split(".") if file.module else []
    if not file.path.endswith("__init__.py"):
        parts = parts[:-1]
    if level > 1:
        parts = parts[: max(0, len(parts) - (level - 1))]
    rest = module.lstrip(".")
    return ".".join([*parts, rest] if rest else parts)


def script_import_module(file: FileNode, module: str) -> str | None:
    """Module of a relative JavaScript or TypeScript import; packages are out of the snapshot."""
    if not module.startswith("."):
        return None
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(file.path), module))
    parts = joined.split("/")
    if parts and parts[0] in {"src", "lib", "app"}:
        parts = parts[1:]
    if len(parts) > 1 and parts[-1] == "index":
        parts = parts[:-1]
    return ".".join(part for part in parts if part not in {"", "."})


class Resolver:
    def __init__(self, files: list[FileNode], symbols: list[SymbolNode]) -> None:
        self.files = files
        self.symbols = {s.id: s for s in symbols}
        self.by_name: dict[str, list[SymbolNode]] = defaultdict(list)
        self.by_file: dict[tuple[int, str], list[SymbolNode]] = defaultdict(list)
        self.modules: dict[str, list[int]] = defaultdict(list)
        for index, file in enumerate(files):
            if file.module:
                self.modules[file.module].append(index)
                if file.language == languages.GO:
                    self.modules[file.module.rsplit(".", 1)[-1]].append(index)
        for symbol in symbols:
            self.by_name[symbol.name].append(symbol)
            self.by_file[(symbol.file, symbol.name)].append(symbol)
        self.aliases = [self._aliases(index, file) for index, file in enumerate(files)]

    def _aliases(self, index: int, file: FileNode) -> dict[str, Alias]:
        table: dict[str, Alias] = {}
        for imported in file.imports:
            if file.language == languages.PYTHON:
                module = python_import_module(file, imported.module)
                if imported.name is None:
                    table[imported.alias] = Alias(module, None)
                elif f"{module}.{imported.name}" in self.modules:
                    table[imported.alias] = Alias(f"{module}.{imported.name}", None)
                else:
                    table[imported.alias] = Alias(module, imported.name)
            elif file.language == languages.GO:
                table[imported.alias] = Alias(imported.module.rsplit("/", 1)[-1], None)
            else:
                script_module = script_import_module(file, imported.module)
                if script_module is None:
                    continue
                name = imported.name if imported.name != "default" else imported.alias
                table[imported.alias] = Alias(script_module, name)
        return table

    def _in_module(self, module: str, name: str) -> SymbolNode | None:
        candidates = [
            symbol
            for file_index in self.modules.get(module, [])
            for symbol in self.by_file.get((file_index, name), [])
        ]
        top = [s for s in candidates if s.parent is None]
        best = top or candidates
        return best[0] if best else None

    def _unique(self, name: str, *, methods: bool) -> SymbolNode | None:
        candidates = [
            s for s in self.by_name.get(name, []) if (s.kind == SymbolKind.METHOD) == methods
        ]
        return candidates[0] if len(candidates) == 1 else None

    def _method_of(self, class_name: str, method: str, prefer_file: int) -> SymbolNode | None:
        classes = [s for s in self.by_name.get(class_name, []) if s.kind in _CLASSLIKE]
        classes.sort(key=lambda s: s.file != prefer_file)
        for cls in classes:
            for candidate in self.by_name.get(method, []):
                if candidate.parent == cls.id:
                    return candidate
        return None

    def _enclosing_class(self, source: SymbolNode | None) -> SymbolNode | None:
        if source is None:
            return None
        if source.kind in _CLASSLIKE:
            return source
        parent = self.symbols.get(source.parent) if source.parent else None
        return parent if parent is not None and parent.kind in _CLASSLIKE else None

    def resolve(
        self, file_index: int, ref: RefDraft, source: SymbolNode | None
    ) -> uuid.UUID | None:
        target = self._resolve(file_index, ref, source)
        return target.id if target is not None and target is not source else None

    def _resolve(
        self, file_index: int, ref: RefDraft, source: SymbolNode | None
    ) -> SymbolNode | None:
        aliases = self.aliases[file_index]
        if ref.kind == RefKind.IMPORT:
            alias = next(
                (a for name, a in aliases.items() if a.name == ref.target or name == ref.target),
                None,
            )
            if alias is not None and alias.name is not None:
                return self._in_module(alias.module, alias.name)
            return None

        qualifier = ref.qualifier
        if qualifier is None:
            local = self.by_file.get((file_index, ref.target), [])
            preferred = [s for s in local if s.kind != SymbolKind.METHOD] or local
            if preferred:
                return preferred[0]
            alias = aliases.get(ref.target)
            if alias is not None:
                return self._in_module(alias.module, alias.name) if alias.name else None
            return self._unique(ref.target, methods=False)

        head = qualifier.split(".", 1)[0]
        if head in _SELF:
            enclosing = self._enclosing_class(source)
            if enclosing is not None:
                for candidate in self.by_name.get(ref.target, []):
                    if candidate.parent == enclosing.id:
                        return candidate
            return self._unique(ref.target, methods=True)
        alias = aliases.get(head)
        if alias is not None and "." not in qualifier:
            if alias.name is None:
                return self._in_module(alias.module, ref.target)
            return self._method_of(alias.name, ref.target, file_index)
        if "." not in qualifier:
            method = self._method_of(qualifier, ref.target, file_index)
            if method is not None:
                return method
        return self._unique(ref.target, methods=True)
