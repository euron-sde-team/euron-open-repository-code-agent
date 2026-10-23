"""Python symbols and references from the standard library `ast`.

Classes, functions, methods (async included) and UPPER_CASE module constants become
symbols. Calls, imports and base classes become references. Functions nested inside other
functions are not separate symbols; their calls count towards the enclosing function,
which is how a reader thinks about them.
"""

from __future__ import annotations

import ast
import re

from codeagent.codeintel.symbols.types import (
    FileOutline,
    ImportDraft,
    RefDraft,
    RefKind,
    SymbolDraft,
    SymbolKind,
    first_paragraph,
    one_line,
)

_CONSTANT = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_TRAILING_COMMENT = re.compile(r"\s*#[^'\"]*$")


def _dotted(node: ast.expr) -> str | None:
    """`a.b.c` for a chain of attribute accesses on a name, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _header(lines: list[str], node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """The `def` or `class` line as the author wrote it, up to the colon before the body.

    Column offsets in `ast` are UTF-8 byte offsets, so lines are sliced as bytes.
    """
    first, body = node.lineno - 1, node.body[0]
    last = min(body.lineno - 1, len(lines) - 1)
    parts: list[str] = []
    for index in range(first, last + 1):
        raw = lines[index].encode()
        start = node.col_offset if index == first else 0
        end = body.col_offset if index == last else len(raw)
        part = raw[start:end].decode("utf-8", "replace").strip()
        parts.append(_TRAILING_COMMENT.sub("", part))
    return one_line(
        " ".join(part for part in parts if part).rstrip().removesuffix(":").rstrip(), 240
    )


def _start(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    return min([node.lineno, *(d.lineno for d in node.decorator_list)])


def _exported_names(tree: ast.Module) -> set[str] | None:
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in statement.targets)
            and isinstance(statement.value, ast.List | ast.Tuple)
        ):
            return {
                element.value
                for element in statement.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    return None


class _Extractor:
    def __init__(self, module: str, exported: set[str] | None, lines: list[str]) -> None:
        self.module = module
        self.lines = lines
        self.exported = exported
        self.outline = FileOutline()

    def _qualified(self, *names: str) -> str:
        return ".".join(part for part in (self.module, *names) if part)

    def _add(self, draft: SymbolDraft) -> int:
        self.outline.symbols.append(draft)
        return draft.key

    def _is_exported(self, name: str, parent: int | None) -> bool:
        if name.startswith("_") and not name.startswith("__"):
            return False
        if parent is None and self.exported is not None:
            return name in self.exported
        return True

    def module_body(self, body: list[ast.stmt]) -> None:
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                self.class_def(statement, parent=None, path=())
            elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                self.function(statement, parent=None, path=(), kind=SymbolKind.FUNCTION)
            elif isinstance(statement, ast.Import | ast.ImportFrom):
                self.import_statement(statement)
            else:
                self.constant(statement)
                self.calls(statement, source=None)

    def class_def(self, node: ast.ClassDef, parent: int | None, path: tuple[str, ...]) -> None:
        key = self._add(
            SymbolDraft(
                key=len(self.outline.symbols),
                name=node.name,
                qualified_name=self._qualified(*path, node.name),
                kind=SymbolKind.CLASS,
                start_line=_start(node),
                end_line=node.end_lineno or node.lineno,
                signature=_header(self.lines, node),
                doc=first_paragraph(ast.get_docstring(node) or ""),
                parent=parent,
                exported=self._is_exported(node.name, parent),
            )
        )
        for base in node.bases:
            name = _dotted(base)
            if name:
                qualifier, _, target = name.rpartition(".")
                self.outline.refs.append(
                    RefDraft(target, RefKind.INHERIT, base.lineno, key, qualifier or None)
                )
        for decorator in node.decorator_list:
            self.calls(decorator, source=key)
        for statement in node.body:
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                self.function(
                    statement, parent=key, path=(*path, node.name), kind=SymbolKind.METHOD
                )
            elif isinstance(statement, ast.ClassDef):
                self.class_def(statement, parent=key, path=(*path, node.name))
            else:
                self.calls(statement, source=key)

    def function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent: int | None,
        path: tuple[str, ...],
        kind: SymbolKind,
    ) -> None:
        key = self._add(
            SymbolDraft(
                key=len(self.outline.symbols),
                name=node.name,
                qualified_name=self._qualified(*path, node.name),
                kind=kind,
                start_line=_start(node),
                end_line=node.end_lineno or node.lineno,
                signature=_header(self.lines, node),
                doc=first_paragraph(ast.get_docstring(node) or ""),
                parent=parent,
                exported=self._is_exported(node.name, parent),
            )
        )
        for decorator in node.decorator_list:
            self.calls(decorator, source=key)
        for statement in node.body:
            self.calls(statement, source=key)

    def constant(self, statement: ast.stmt) -> None:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        for target in targets:
            if (
                isinstance(target, ast.Name)
                and _CONSTANT.match(target.id)
                and target.id != "__all__"
            ):
                preview = ast.unparse(value) if value is not None else ""
                self._add(
                    SymbolDraft(
                        key=len(self.outline.symbols),
                        name=target.id,
                        qualified_name=self._qualified(target.id),
                        kind=SymbolKind.CONSTANT,
                        start_line=statement.lineno,
                        end_line=statement.end_lineno or statement.lineno,
                        signature=one_line(f"{target.id} = {preview}", 160),
                        exported=self._is_exported(target.id, None),
                    )
                )

    def import_statement(self, statement: ast.Import | ast.ImportFrom) -> None:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                local = alias.asname or alias.name.split(".")[0]
                self.outline.imports.append(ImportDraft(local, alias.name, None, statement.lineno))
                self.outline.refs.append(
                    RefDraft(
                        alias.name.rsplit(".", 1)[-1],
                        RefKind.IMPORT,
                        statement.lineno,
                        None,
                        alias.name,
                    )
                )
            return
        module = "." * statement.level + (statement.module or "")
        for alias in statement.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self.outline.imports.append(ImportDraft(local, module, alias.name, statement.lineno))
            self.outline.refs.append(
                RefDraft(alias.name, RefKind.IMPORT, statement.lineno, None, module or None)
            )

    def calls(self, node: ast.AST, source: int | None) -> None:
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name):
                self.outline.refs.append(RefDraft(func.id, RefKind.CALL, child.lineno, source))
            elif isinstance(func, ast.Attribute):
                qualifier = _dotted(func.value)
                self.outline.refs.append(
                    RefDraft(func.attr, RefKind.CALL, child.lineno, source, qualifier)
                )


def extract_python(source: str, *, module: str = "") -> FileOutline:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        where = f" (line {line})" if line else ""
        return FileOutline(error=f"Python syntax error{where}: {getattr(exc, 'msg', str(exc))}")
    extractor = _Extractor(module, _exported_names(tree), source.splitlines())
    extractor.module_body(tree.body)
    return extractor.outline


def module_name(path: str) -> str:
    """`src/ledgerkit/money.py` -> `ledgerkit.money`; `pkg/__init__.py` -> `pkg`."""
    parts = path.removesuffix(".pyi").removesuffix(".py").split("/")
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)
