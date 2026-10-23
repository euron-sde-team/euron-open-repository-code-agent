"""Small, targeted source mutations: the search space for repairing a failing test.

Most single-line bugs in business logic are one of a handful of shapes: a boundary that is
strict when it should not be (`>` for `>=`), a comparison pointing the wrong way, an
off-by-one constant, the wrong boolean operator, a sign error, or the wrong rounding mode.
This module enumerates those edits inside one function, each as an exact character-range
replacement, ranked by how often that shape is the culprit.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass

_COMPARE_SWAPS: dict[str, tuple[tuple[str, int, str], ...]] = {
    # operator: ((replacement, priority, description), ...)
    "<": (("<=", 1, "make the boundary inclusive"), (">", 3, "reverse the comparison")),
    "<=": (("<", 1, "make the boundary exclusive"), (">=", 3, "reverse the comparison")),
    ">": ((">=", 1, "make the boundary inclusive"), ("<", 3, "reverse the comparison")),
    ">=": ((">", 1, "make the boundary exclusive"), ("<=", 3, "reverse the comparison")),
    "==": (("!=", 3, "negate the equality"),),
    "!=": (("==", 3, "negate the inequality"),),
}
_ROUNDING = ("ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_HALF_DOWN", "ROUND_DOWN", "ROUND_UP")
_OPERATOR = re.compile(r"<=|>=|==|!=|<|>")
Adder = Callable[[int, int, int, str, str, float], None]


@dataclass(frozen=True, slots=True)
class Mutation:
    line: int  # 1-based
    start: int  # character offsets within the line
    end: int
    replacement: str
    original: str
    description: str
    priority: float

    def apply(self, source: str) -> str:
        lines = source.splitlines(keepends=True)
        text = lines[self.line - 1]
        lines[self.line - 1] = text[: self.start] + self.replacement + text[self.end :]
        return "".join(lines)

    def summary(self, source: str) -> str:
        code = source.splitlines()[self.line - 1].strip()
        change = f"`{self.original}` to `{self.replacement}`"
        return f"line {self.line}: {change} ({self.description}) in `{code}`"


def _char(line: str, byte_offset: int) -> int:
    return len(line.encode("utf-8")[:byte_offset].decode("utf-8", "ignore"))


def _between(lines: list[str], left: ast.expr, right: ast.expr) -> tuple[int, int, int] | None:
    """(line, start, end) of the text between two expressions on the same line."""
    if left.end_lineno != right.lineno or left.end_col_offset is None:
        return None
    line = lines[right.lineno - 1]
    return right.lineno, _char(line, left.end_col_offset), _char(line, right.col_offset)


def mutations(source: str, start_line: int, end_line: int, hints: set[str]) -> list[Mutation]:
    """Candidate edits inside lines [start_line, end_line], best first.

    `hints` are literals from the failure message (`100`, `0.9`): constants equal to one of
    them rank higher, because the failing assertion is usually about that boundary.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    found: list[Mutation] = []
    seen: set[tuple[int, int, str]] = set()

    def add(
        line: int, start: int, end: int, replacement: str, description: str, priority: float
    ) -> None:
        original = lines[line - 1][start:end]
        key = (line, start, replacement)
        if original != replacement and key not in seen:
            seen.add(key)
            found.append(Mutation(line, start, end, replacement, original, description, priority))

    for node in ast.walk(tree):
        node_line = getattr(node, "lineno", 0)
        if not start_line <= node_line <= end_line:
            continue
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for index in range(len(node.ops)):
                span = _between(lines, operands[index], operands[index + 1])
                if span is None:
                    continue
                line, start, end = span
                match = _OPERATOR.search(lines[line - 1][start:end])
                if match is None:
                    continue
                op_start, op_end = start + match.start(), start + match.end()
                for replacement, priority, description in _COMPARE_SWAPS.get(match.group(), ()):
                    add(line, op_start, op_end, replacement, description, priority)
            for comparator in operands:
                _constant(comparator, lines, hints, add, base=2.0)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
        ):
            for argument in node.args:
                _constant(argument, lines, hints, add, base=2.0)
        elif isinstance(node, ast.BoolOp):
            word, other = ("and", "or") if isinstance(node.op, ast.And) else ("or", "and")
            for left, right in zip(node.values, node.values[1:], strict=False):
                span = _between(lines, left, right)
                if span is None:
                    continue
                line, start, end = span
                position = lines[line - 1].find(f" {word} ", start, end)
                if position >= 0:
                    add(line, position + 1, position + 1 + len(word), other, f"use `{other}`", 3.5)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub):
            span = _between(lines, node.left, node.right)
            if span is None:
                continue
            line, start, end = span
            symbol, other = ("+", "-") if isinstance(node.op, ast.Add) else ("-", "+")
            position = lines[line - 1].find(symbol, start, end)
            if position >= 0:
                add(line, position, position + 1, other, "flip the sign", 4.0)
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in _ROUNDING and node.end_col_offset is not None:
                line = node.end_lineno or node_line
                end = _char(lines[line - 1], node.end_col_offset)
                start = end - len(name)
                for other in _ROUNDING[:2]:
                    if other != name and other in source:
                        add(line, start, end, other, f"round with {other}", 2.0)
    found.sort(key=lambda m: (m.priority, m.line, m.start))
    return found


def _constant(
    node: ast.expr, lines: list[str], hints: set[str], add: Adder, *, base: float
) -> None:
    if not (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
        and node.end_col_offset is not None
        and node.lineno == node.end_lineno
    ):
        return
    line = lines[node.lineno - 1]
    start, end = _char(line, node.col_offset), _char(line, node.end_col_offset)
    if not line[start:end].isdigit():
        return
    priority = base - 0.5 if str(node.value) in hints else base
    for delta in (1, -1):
        value = node.value + delta
        if value >= 0:
            add(node.lineno, start, end, str(value), f"change {node.value} to {value}", priority)
