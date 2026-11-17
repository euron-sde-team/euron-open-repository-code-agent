"""The model planner's answer format: a plan, a rationale and search-and-replace edits.

    PLAN:
    1. ...
    RATIONALE:
    ...
    EDITS:
    path/to/file.py
    <<<<<<< SEARCH
    exact lines from the file
    =======
    the replacement lines
    >>>>>>> REPLACE

Search-and-replace blocks are robust to line-number drift and easy for models to produce.
A block whose SEARCH text is not found exactly is retried ignoring indentation and trailing
spaces; a block that still does not match fails the run with the block quoted, rather than
guessing where it was meant to go. An empty SEARCH creates (or replaces) a whole file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_BLOCK = re.compile(
    r"^(?P<path>[^\n<>=]+?)\s*\n(?:```[^\n]*\n)?<{7} SEARCH\n"
    r"(?P<search>.*?)^={7}\n(?P<replace>.*?)^>{7} REPLACE",
    re.DOTALL | re.MULTILINE,
)
_SECTION = re.compile(r"^(PLAN|RATIONALE|EDITS):\s*$", re.MULTILINE)
_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*\S)\s*$")


class EditError(Exception):
    def __init__(self, message: str, block: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.block = block[:1200]


@dataclass(frozen=True, slots=True)
class Edit:
    path: str
    search: str
    replace: str


@dataclass(slots=True)
class ModelPlan:
    steps: list[str] = field(default_factory=list)
    rationale: str = ""
    edits: list[Edit] = field(default_factory=list)


def _clean_path(raw: str) -> str:
    path = raw.strip().strip("`*").strip()
    path = path.removeprefix("./")
    if not path or path.startswith("/") or ".." in path.split("/") or len(path) > 300:
        raise EditError(f"The edit names an unsafe or empty path: {raw.strip()!r}")
    return path


def parse(text: str) -> ModelPlan:
    sections: dict[str, str] = {}
    matches = list(_SECTION.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.end() : end].strip("\n")
    plan = ModelPlan()
    for line in sections.get("PLAN", "").splitlines():
        step = _STEP.match(line)
        if step:
            plan.steps.append(step.group(1))
    plan.rationale = sections.get("RATIONALE", "").strip()
    for block in _BLOCK.finditer(sections.get("EDITS", text)):
        plan.edits.append(
            Edit(_clean_path(block.group("path")), block.group("search"), block.group("replace"))
        )
    return plan


def _normalized(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines]


def apply_edit(content: str | None, edit: Edit) -> str:
    """The file content after one edit. Raises EditError when SEARCH cannot be placed."""
    if not edit.search.strip():
        if content is not None and content.strip():
            # An empty SEARCH creates a file; on an existing one it would silently replace it.
            raise EditError(
                f"{edit.path} already exists, so an edit to it needs a SEARCH block.", edit.replace
            )
        return edit.replace
    if content is None:
        raise EditError(
            f"{edit.path} does not exist, so its SEARCH text cannot match.", edit.search
        )
    if edit.search in content:
        return content.replace(edit.search, edit.replace, 1)
    # Retry ignoring indentation and trailing whitespace, line by line.
    lines = content.splitlines(keepends=True)
    wanted = _normalized(edit.search.splitlines())
    while wanted and not wanted[-1]:
        wanted.pop()
    if not wanted:
        raise EditError(f"An edit to {edit.path} has an empty SEARCH block.", edit.search)
    stripped = _normalized(lines)
    for start in range(len(lines) - len(wanted) + 1):
        if stripped[start : start + len(wanted)] == wanted:
            replacement = edit.replace
            if replacement and not replacement.endswith("\n"):
                replacement += "\n"
            return "".join([*lines[:start], replacement, *lines[start + len(wanted) :]])
    raise EditError(
        f"The SEARCH text of an edit to {edit.path} was not found in the file.", edit.search
    )


def apply_edits(files: dict[str, str | None], edits: list[Edit]) -> dict[str, str]:
    """Apply edits in order; returns the new content of every file an edit touched."""
    changed: dict[str, str] = {}
    for edit in edits:
        current = changed.get(edit.path, files.get(edit.path))
        changed[edit.path] = apply_edit(current, edit)
    return changed
