"""Unified diffs: building them git-style from file contents, and parsing them for review.

`build_patch` produces exactly what `git diff` would for the same change (`diff --git`
headers, `new file mode`, `/dev/null` sides, `\\ No newline at end of file`), so the result
applies with `git apply` and `git am`. `parse_patch` turns a patch back into files, hunks
and numbered lines for the diff viewer and for anchoring review comments.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

NO_NEWLINE = "\\ No newline at end of file"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass(frozen=True, slots=True)
class FileChange:
    """A whole-file change. `old` None: the file is new. `new` None: the file is deleted."""

    path: str
    old: str | None
    new: str | None

    @property
    def change_type(self) -> str:
        if self.old is None:
            return "added"
        if self.new is None:
            return "deleted"
        return "modified"


@dataclass(frozen=True, slots=True)
class FileStat:
    path: str
    change_type: str
    additions: int
    deletions: int


def _lines(text: str | None) -> list[str]:
    return [] if text is None else text.splitlines(keepends=True)


def file_diff(change: FileChange, context: int = 3) -> str:
    """The git-style diff of one file, or "" when nothing changed."""
    if change.old == change.new:
        return ""
    old_name = "/dev/null" if change.old is None else f"a/{change.path}"
    new_name = "/dev/null" if change.new is None else f"b/{change.path}"
    header = [f"diff --git a/{change.path} b/{change.path}\n"]
    if change.old is None:
        header.append("new file mode 100644\n")
    elif change.new is None:
        header.append("deleted file mode 100644\n")
    body: list[str] = []
    for line in difflib.unified_diff(
        _lines(change.old), _lines(change.new), old_name, new_name, n=context
    ):
        if line.endswith("\n"):
            body.append(line)
        else:
            body.append(f"{line}\n{NO_NEWLINE}\n")
    if not body:
        return ""
    return "".join(header + body)


def build_patch(changes: list[FileChange]) -> str:
    return "".join(file_diff(change) for change in sorted(changes, key=lambda c: c.path))


def stats(changes: list[FileChange]) -> list[FileStat]:
    result = []
    for change in sorted(changes, key=lambda c: c.path):
        additions = deletions = 0
        for line in difflib.unified_diff(_lines(change.old), _lines(change.new), n=0):
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        if additions or deletions or change.old != change.new:
            result.append(FileStat(change.path, change.change_type, additions, deletions))
    return result


@dataclass(slots=True)
class DiffLine:
    kind: str  # "context" | "add" | "del"
    text: str
    old_line: int | None
    new_line: int | None


@dataclass(slots=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass(slots=True)
class PatchFile:
    path: str
    old_path: str | None
    change_type: str
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def additions(self) -> int:
        return sum(1 for h in self.hunks for line in h.lines if line.kind == "add")

    @property
    def deletions(self) -> int:
        return sum(1 for h in self.hunks for line in h.lines if line.kind == "del")


def parse_patch(patch: str) -> list[PatchFile]:
    files: list[PatchFile] = []
    current: PatchFile | None = None
    hunk: Hunk | None = None
    old_no = new_no = 0
    for raw in patch.split("\n"):
        if raw.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+) b/(.+)$", raw)
            path = match.group(2) if match else raw.split(" b/", 1)[-1]
            current = PatchFile(
                path=path, old_path=match.group(1) if match else None, change_type="modified"
            )
            files.append(current)
            hunk = None
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current.change_type = "added"
        elif raw.startswith("deleted file mode"):
            current.change_type = "deleted"
        elif raw.startswith(("--- ", "+++ ")) and hunk is None:
            continue
        elif raw.startswith("@@"):
            match = _HUNK.match(raw)
            if not match:
                continue
            old_no, new_no = int(match.group(1)), int(match.group(3))
            hunk = Hunk(
                old_start=old_no,
                old_count=int(match.group(2) or 1),
                new_start=new_no,
                new_count=int(match.group(4) or 1),
                section=match.group(5).strip(),
            )
            current.hunks.append(hunk)
        elif hunk is not None and raw.startswith("+"):
            hunk.lines.append(DiffLine("add", raw[1:], None, new_no))
            new_no += 1
        elif hunk is not None and raw.startswith("-"):
            hunk.lines.append(DiffLine("del", raw[1:], old_no, None))
            old_no += 1
        elif hunk is not None and raw.startswith(" "):
            hunk.lines.append(DiffLine("context", raw[1:], old_no, new_no))
            old_no += 1
            new_no += 1
    return files
