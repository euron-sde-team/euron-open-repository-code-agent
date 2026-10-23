"""Small, formatting-preserving edits to Python modules: imports, definitions, `__all__`.

Edits are made on the text, guided by `ast` positions, so the rest of the file keeps its
exact formatting and the diff shows only what changed.
"""

from __future__ import annotations

import ast
import re

_FROM = re.compile(r"^from\s+(\S+)\s+import\s+(.+)$")
_IMPORT = re.compile(r"^import\s+(\S+)(?:\s+as\s+\S+)?$")


def _tree(source: str) -> ast.Module:
    return ast.parse(source)


def defines(source: str, name: str) -> bool:
    for node in _tree(source).body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and node.name == name
        ):
            return True
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return True
    return False


def _imported(tree: ast.Module) -> tuple[set[str], dict[str, ast.ImportFrom]]:
    modules: set[str] = set()
    froms: dict[str, ast.ImportFrom] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            froms.setdefault(node.module, node)
    return modules, froms


def _insert_line(tree: ast.Module, lines: list[str]) -> int:
    """Index (0-based) of the line after the last top-level import, or after the docstring."""
    last = 0
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom) or (
            last == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            last = node.end_lineno or node.lineno
    if last == 0:
        return 0
    return last


def insert_imports(source: str, imports: list[str]) -> str:
    """Add `import x` and `from x import a, b` lines that the module does not have yet."""
    for statement in imports:
        tree = _tree(source)
        modules, froms = _imported(tree)
        lines = source.splitlines(keepends=True)
        from_match = _FROM.match(statement)
        if from_match:
            module = from_match.group(1)
            wanted = [n.strip() for n in from_match.group(2).split(",") if n.strip()]
            existing = froms.get(module)
            if existing is not None:
                have = {alias.asname or alias.name for alias in existing.names}
                missing = [name for name in wanted if name not in have]
                if not missing:
                    continue
                if existing.lineno == existing.end_lineno:
                    merged = ast.ImportFrom(
                        module=module,
                        names=[*existing.names, *(ast.alias(name=n) for n in missing)],
                        level=0,
                    )
                    lines[existing.lineno - 1] = ast.unparse(merged) + "\n"
                    source = "".join(lines)
                    continue
            line = f"from {module} import {', '.join(wanted)}\n"
        else:
            import_match = _IMPORT.match(statement)
            if import_match and import_match.group(1) in modules:
                continue
            line = statement.rstrip() + "\n"
        index = _insert_line(tree, lines)
        if index == 0:
            lines.insert(0, line + ("\n" if lines and lines[0].strip() else ""))
        else:
            lines.insert(index, line)
        source = "".join(lines)
    return source


def append_definition(source: str, code: str) -> str:
    """Add a top-level definition at the end (before a `__main__` block), two blank lines apart."""
    tree = _tree(source)
    lines = source.splitlines(keepends=True)
    main_block = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ),
        None,
    )
    block = code.strip("\n") + "\n"
    if main_block is not None:
        head = "".join(lines[: main_block.lineno - 1]).rstrip("\n")
        tail = "".join(lines[main_block.lineno - 1 :])
        return f"{head}\n\n\n{block}\n\n{tail}"
    body = source.rstrip("\n")
    return f"{body}\n\n\n{block}" if body else block


def add_to_all(source: str, name: str) -> str:
    """Append `name` to a literal `__all__` list or tuple, keeping its layout."""
    tree = _tree(source)
    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
            and isinstance(node.value, ast.List | ast.Tuple)
        ):
            continue
        values = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
        if name in values:
            return source
        lines = source.splitlines(keepends=True)
        end_line = node.value.end_lineno or node.lineno
        closing = lines[end_line - 1]
        bracket = closing.rfind("]" if isinstance(node.value, ast.List) else ")")
        if node.value.lineno != end_line and closing[:bracket].strip() == "":
            previous = lines[end_line - 2]
            indent = previous[: len(previous) - len(previous.lstrip())] or "    "
            if previous.rstrip() and not previous.rstrip().endswith(","):
                lines[end_line - 2] = previous.rstrip("\n") + ",\n"
            lines.insert(end_line - 1, f'{indent}"{name}",\n')
            return "".join(lines)
        before = closing[:bracket].rstrip()
        if before.endswith(("[", "(")):
            separator = ""
        elif before.endswith(","):
            separator = " "
        else:
            separator = ", "
        lines[end_line - 1] = f'{before}{separator}"{name}"{closing[bracket:]}'
        return "".join(lines)
    return source
