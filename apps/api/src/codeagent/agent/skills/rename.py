"""Rename a symbol everywhere the reference graph says it is used.

Only identifier tokens change, never comments or prose. Strings change in two exact cases
that are references in disguise: the symbol's name inside `__all__`, and its dotted path
(`"ledgerkit.tax.calc_tax"`, as passed to `mock.patch`). Which identifiers change depends
on the kind of symbol:

- a function, class or constant: every bare occurrence in its own file and in files that
  import it by name, plus attribute accesses (`tax.calc_tax`) on lines where the index
  resolved a reference to it;
- a method: its `def` line, `self.name` and `cls.name` inside its class, and attribute
  accesses on lines where the index resolved a reference to it.
"""

from __future__ import annotations

import ast
import keyword
import re
from dataclasses import dataclass

from codeagent.agent.diffs import FileChange
from codeagent.agent.tokens import Tok, TokenizeError, apply_replacements, tokens_for
from codeagent.agent.types import (
    Note,
    PlannerError,
    PlanResult,
    PlanStep,
    RepoView,
    SymbolInfo,
    TaskSpec,
)

PATTERN = re.compile(
    r"\brename\s+(?:the\s+)?(?:function|method|class|constant|variable|symbol|helper|attribute)?\s*"
    r"`?(?P<old>[A-Za-z_][\w.]*)`?\s+(?:to|as|into)\s+`?(?P<new>[A-Za-z_]\w*)`?",
    re.IGNORECASE,
)
_SELF = frozenset({"self", "cls", "this"})


@dataclass(frozen=True, slots=True)
class RenameRequest:
    old: str
    new: str
    owner: str | None  # class name for `Class.method`


def parse_request(task: TaskSpec) -> RenameRequest | None:
    match = PATTERN.search(task.text)
    if not match:
        return None
    old = match.group("old").strip(".")
    owner, _, name = old.rpartition(".")
    return RenameRequest(old=name, new=match.group("new"), owner=owner.rsplit(".", 1)[-1] or None)


def _all_ranges(source: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    ranges = []
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


async def _choose(view: RepoView, request: RenameRequest) -> SymbolInfo:
    candidates = [
        s
        for s in await view.index.by_name(request.old)
        if not view.files.get(s.path) or not view.files[s.path].is_test
    ]
    if request.owner:
        candidates = [s for s in candidates if s.parent_name == request.owner]
    if not candidates:
        where = f" on `{request.owner}`" if request.owner else ""
        raise PlannerError(
            "symbol_not_found", f"No symbol named `{request.old}`{where} is in the index."
        )
    top = [s for s in candidates if s.kind != "method"]
    chosen = (top or candidates)[0]
    if len({(s.path, s.qualified_name) for s in (top or candidates)}) > 1:
        names = ", ".join(f"`{s.qualified_name}`" for s in (top or candidates)[:5])
        raise PlannerError(
            "ambiguous_symbol",
            f"`{request.old}` is defined more than once ({names}). Name the class or module, "
            "for example `Class.method`.",
        )
    return chosen


async def _check_new_name(view: RepoView, symbol: SymbolInfo, new: str) -> None:
    if not new.isidentifier() or keyword.iskeyword(new):
        raise PlannerError("invalid_name", f"`{new}` is not a valid identifier.")
    for existing in await view.index.by_name(new):
        same_scope = existing.parent_name == symbol.parent_name and (
            existing.path == symbol.path or symbol.kind == "method"
        )
        if same_scope:
            raise PlannerError(
                "name_taken",
                f"`{new}` already exists in `{existing.path}` (line {existing.start_line}).",
            )


def _rename_file(
    source: str,
    tokens: list[Tok],
    symbol: SymbolInfo,
    new: str,
    *,
    bare: bool,
    attribute_lines: set[int],
    class_range: tuple[int, int] | None,
) -> tuple[str, int]:
    old = symbol.name
    dotted_old = symbol.qualified_name
    dotted_new = f"{dotted_old.rsplit('.', 1)[0]}.{new}" if "." in dotted_old else new
    all_ranges = _all_ranges(source)
    replacements: list[tuple[Tok, str]] = []
    previous: Tok | None = None
    before_previous: Tok | None = None
    for tok in tokens:
        if tok.kind == "name" and tok.text == old:
            after_dot = previous is not None and previous.kind == "op" and previous.text == "."
            if not after_dot:
                is_definition = tok.line == symbol.start_line or (
                    previous is not None and previous.text in {"def", "class", "function", "func"}
                )
                if bare or (symbol.kind == "method" and is_definition):
                    replacements.append((tok, new))
            else:
                owner = before_previous.text if before_previous is not None else ""
                inside_class = (
                    class_range is not None and class_range[0] <= tok.line <= class_range[1]
                )
                if tok.line in attribute_lines or (owner in _SELF and inside_class):
                    replacements.append((tok, new))
        elif tok.kind == "string":
            body = tok.text.strip("'\"")
            in_all = any(start <= tok.line <= end for start, end in all_ranges)
            if (body == old and in_all) or body == dotted_old:
                quote = tok.text[0]
                replacements.append(
                    (tok, f"{quote}{dotted_new if body == dotted_old else new}{quote}")
                )
        before_previous, previous = previous, tok
    return apply_replacements(source, replacements), len(replacements)


async def rename(task: TaskSpec, view: RepoView, note: Note) -> PlanResult:
    request = parse_request(task)
    if request is None:
        raise PlannerError(
            "unrecognised", "Describe the rename as: rename `old_name` to `new_name`."
        )
    symbol = await _choose(view, request)
    await _check_new_name(view, symbol, request.new)
    await note(
        f"Found {symbol.kind} `{symbol.qualified_name}` in `{symbol.path}` "
        f"(line {symbol.start_line})."
    )

    refs = await view.index.refs_to(symbol.id)
    importing = {ref.path for ref in refs if ref.kind == "import"}
    attribute_lines: dict[str, set[int]] = {}
    for ref in refs:
        attribute_lines.setdefault(ref.path, set()).add(ref.line)
    class_range: tuple[int, int] | None = None
    if symbol.kind == "method" and symbol.parent_name:
        owner = next(
            (s for s in await view.index.by_name(symbol.parent_name) if s.path == symbol.path), None
        )
        class_range = (owner.start_line, owner.end_line) if owner else None

    paths = {symbol.path} | importing | set(attribute_lines)
    changes: list[FileChange] = []
    total = 0
    for path in sorted(paths):
        info = view.files.get(path)
        if info is None or not view.exists(path):
            continue
        source = view.read(path)
        try:
            tokens = tokens_for(source, info.language, path)
        except TokenizeError as exc:
            raise PlannerError("unparseable", f"`{path}` could not be tokenized: {exc}") from exc
        bare = symbol.kind != "method" and (path == symbol.path or path in importing)
        updated, count = _rename_file(
            source,
            tokens,
            symbol,
            request.new,
            bare=bare,
            attribute_lines=attribute_lines.get(path, set()),
            class_range=class_range if path == symbol.path else None,
        )
        if updated != source:
            changes.append(FileChange(path, source, updated))
            total += count
    if not changes:
        raise PlannerError(
            "nothing_to_change", f"No occurrence of `{request.old}` could be renamed."
        )
    await note(f"Renamed {total} occurrence(s) across {len(changes)} file(s).")
    others = len(changes) - 1
    rationale = (
        f"Renames `{symbol.qualified_name}` to `{request.new}`: the definition in "
        f"`{symbol.path}` and every reference the index resolved to it, {total} occurrence(s) in "
        f"{len(changes)} file(s). Only identifiers changed; comments and other strings were "
        "left alone, except exact references in `__all__` and dotted import paths "
        "(such as targets of `mock.patch`), which would otherwise break at run time."
    )
    return PlanResult(
        skill="rename",
        summary=f"Rename `{request.old}` to `{request.new}`",
        plan=[
            PlanStep(
                "Locate the symbol", f"{symbol.kind} `{symbol.qualified_name}` in `{symbol.path}`"
            ),
            PlanStep(
                "Collect references",
                f"{len(refs)} resolved reference(s) in {len(paths)} file(s), "
                f"{len(importing)} importing it by name",
            ),
            PlanStep(
                "Rewrite identifiers",
                f"{total} token(s) in `{symbol.path}`"
                + (f" and {others} other file(s)" if others else ""),
            ),
            PlanStep("Run the tests", "before and after the change, in the sandbox"),
        ],
        rationale=rationale,
        changes=changes,
    )
