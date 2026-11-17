"""Diffs must be exactly what git would write, because `git apply` and `git am` read them."""

from __future__ import annotations

import subprocess
from pathlib import Path

from codeagent.agent.diffs import FileChange, build_patch, parse_patch, stats


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


CHANGES = [
    FileChange("app/pricing.py", "def f(x):\n    return x > 1000\n", "def f(x):\n    return x >= 1000\n"),
    FileChange("app/new.py", None, "VALUE = 1\n"),
    FileChange("app/old.py", "gone\n", None),
]


def test_a_patch_applies_with_git(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "app").mkdir()
    (tmp_path / "app/pricing.py").write_text(CHANGES[0].old or "")
    (tmp_path / "app/old.py").write_text("gone\n")
    patch = build_patch(CHANGES)
    (tmp_path / "change.patch").write_text(patch)
    assert git(tmp_path, "apply", "--check", "change.patch").returncode == 0
    assert git(tmp_path, "apply", "change.patch").returncode == 0
    assert (tmp_path / "app/pricing.py").read_text() == CHANGES[0].new
    assert (tmp_path / "app/new.py").read_text() == "VALUE = 1\n"
    assert not (tmp_path / "app/old.py").exists()


def test_change_types_and_statistics() -> None:
    assert [c.change_type for c in CHANGES] == ["modified", "added", "deleted"]
    by_path = {s.path: s for s in stats(CHANGES)}
    assert (by_path["app/pricing.py"].additions, by_path["app/pricing.py"].deletions) == (1, 1)
    assert (by_path["app/new.py"].additions, by_path["app/new.py"].deletions) == (1, 0)
    assert (by_path["app/old.py"].additions, by_path["app/old.py"].deletions) == (0, 1)


def test_unchanged_files_produce_no_diff() -> None:
    assert build_patch([FileChange("a.py", "x\n", "x\n")]) == ""


def test_a_missing_trailing_newline_is_marked() -> None:
    patch = build_patch([FileChange("a.txt", "one\n", "one\ntwo")])
    assert "\\ No newline at end of file" in patch


def test_parsing_recovers_files_hunks_and_line_numbers() -> None:
    files = parse_patch(build_patch(CHANGES))
    assert [f.path for f in files] == ["app/new.py", "app/old.py", "app/pricing.py"] or {
        f.path for f in files
    } == {"app/pricing.py", "app/new.py", "app/old.py"}
    pricing = next(f for f in files if f.path == "app/pricing.py")
    hunk = pricing.hunks[0]
    kinds = [line.kind for line in hunk.lines]
    assert kinds.count("add") == 1
    assert kinds.count("del") == 1
    deleted = next(line for line in hunk.lines if line.kind == "del")
    added = next(line for line in hunk.lines if line.kind == "add")
    assert deleted.old_line == 2 and deleted.new_line is None
    assert added.new_line == 2 and added.old_line is None
    assert (pricing.additions, pricing.deletions) == (1, 1)


def test_an_added_file_parses_as_added() -> None:
    files = parse_patch(build_patch([FileChange("n.py", None, "a\nb\n")]))
    assert files[0].change_type == "added"
    assert files[0].additions == 2
