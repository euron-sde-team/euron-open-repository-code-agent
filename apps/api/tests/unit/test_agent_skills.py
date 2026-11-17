"""The offline planner's skills against the ledgerkit sample, with no database or sandbox."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from codeagent.agent.diffs import FileChange
from codeagent.agent.planners import LocalPlanner
from codeagent.agent.types import HarnessResult, PlannerError, TaskSpec
from codeagent.codeintel.builder import IndexBuild
from tests.conftest import REPOS
from tests.unit.memory_index import view_of


class NoHarness:
    baseline: HarnessResult | None = None

    async def run(self, changes: list[FileChange], *, purpose: str) -> HarnessResult:
        raise AssertionError("this skill must not run tests itself")

    async def probe(self, candidates: list, tests: list[str]) -> list:  # type: ignore[type-arg]
        raise AssertionError("this skill must not probe")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    target = tmp_path / "ledgerkit"
    shutil.copytree(REPOS / "ledgerkit", target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


async def plan(task: TaskSpec, tree: Path, build: IndexBuild):  # type: ignore[no-untyped-def]
    notes: list[str] = []

    async def note(message: str) -> None:
        notes.append(message)

    result = await LocalPlanner(10).plan(task, view_of(tree, build), NoHarness(), note)
    return result, notes


def apply(result, tree: Path) -> None:  # type: ignore[no-untyped-def]
    for change in result.changes:
        target = tree / change.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if change.new is None:
            target.unlink()
        else:
            target.write_text(change.new)


async def test_rename_rewrites_definition_imports_calls_and_tests(
    tree: Path, ledgerkit: IndexBuild
) -> None:
    task = TaskSpec("Rename it", "rename `apply_discount` to `apply_threshold_discount`")
    result, _ = await plan(task, tree, ledgerkit)
    assert result.skill == "rename"
    paths = {c.path for c in result.changes}
    assert {"ledgerkit/pricing.py", "ledgerkit/invoice.py", "tests/test_pricing.py"} <= paths
    for change in result.changes:
        assert change.new is not None
        assert "apply_discount" not in change.new.replace("apply_discount_", "")
    # Strings and comments are not identifiers: the docstring wording survives.
    pricing = next(c for c in result.changes if c.path == "ledgerkit/pricing.py")
    assert pricing.new is not None
    assert "def apply_threshold_discount(" in pricing.new


def pytest_in(tree: Path, *args: str) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout.strip().splitlines()[-1]


async def test_the_renamed_tree_behaves_exactly_as_before(
    tree: Path, ledgerkit: IndexBuild
) -> None:
    before = pytest_in(tree)
    task = TaskSpec("Rename", "rename `volume_discount` to `quantity_discount`")
    result, _ = await plan(task, tree, ledgerkit)
    apply(result, tree)
    assert "quantity_discount" in (tree / "ledgerkit" / "pricing.py").read_text()
    assert "volume_discount" not in (tree / "ledgerkit" / "invoice.py").read_text()
    after = pytest_in(tree)
    # The sample has one deliberately failing test; the rename must not change the outcome.
    assert after[1].split(" in ")[0] == before[1].split(" in ")[0]


@pytest.mark.parametrize(
    ("description", "code"),
    [
        ("rename `apply_discount` to `not valid`", "invalid_name"),
        ("rename `apply_discount` to `volume_discount`", "name_taken"),
        ("rename `apply_discount` to `class`", "invalid_name"),
        ("rename `does_not_exist` to `something`", "symbol_not_found"),
    ],
)
async def test_rename_refuses_what_it_cannot_do_safely(
    tree: Path, ledgerkit: IndexBuild, description: str, code: str
) -> None:
    with pytest.raises(PlannerError) as caught:
        await plan(TaskSpec("Rename", description), tree, ledgerkit)
    assert caught.value.code == code


async def test_adding_a_catalogued_helper_writes_code_and_tests(
    tree: Path, ledgerkit: IndexBuild
) -> None:
    task = TaskSpec("Add clamp", "add `clamp` to ledgerkit/pricing.py")
    result, _ = await plan(task, tree, ledgerkit)
    assert result.skill == "add_function"
    source = next(c for c in result.changes if c.path == "ledgerkit/pricing.py")
    tests = next(c for c in result.changes if c.path.startswith("tests/"))
    assert source.new is not None and "def clamp(" in source.new
    assert tests.new is not None and "from ledgerkit.pricing import" in tests.new
    assert "def test_clamp" in tests.new


async def test_example_lines_in_the_description_become_tests(
    tree: Path, ledgerkit: IndexBuild
) -> None:
    task = TaskSpec(
        "Add clamp", "add `clamp` to ledgerkit/pricing.py\nExamples:\nclamp(15, 0, 10) == 10"
    )
    result, _ = await plan(task, tree, ledgerkit)
    tests = next(c for c in result.changes if c.path.startswith("tests/"))
    assert tests.new is not None
    assert "clamp(15, 0, 10) == 10" in tests.new


async def test_the_added_helper_passes_its_own_tests(tree: Path, ledgerkit: IndexBuild) -> None:
    result, _ = await plan(
        TaskSpec("Add", "add `safe_divide` to ledgerkit/pricing.py"), tree, ledgerkit
    )
    apply(result, tree)
    code, summary = pytest_in(tree, "tests/test_pricing.py", "-k", "safe_divide")
    assert code == 0, summary
    assert "passed" in summary


async def test_a_helper_that_already_exists_is_not_added_twice(
    tree: Path, ledgerkit: IndexBuild
) -> None:
    first, _ = await plan(TaskSpec("Add", "add `clamp` to ledgerkit/pricing.py"), tree, ledgerkit)
    apply(first, tree)
    with pytest.raises(PlannerError) as caught:
        await plan(TaskSpec("Add", "add `clamp` to ledgerkit/pricing.py"), tree, ledgerkit)
    assert caught.value.code == "already_exists"


async def test_unknown_helpers_explain_what_is_available(tree: Path, ledgerkit: IndexBuild) -> None:
    with pytest.raises(PlannerError) as caught:
        await plan(TaskSpec("Add", "add `frobnicate` to ledgerkit/pricing.py"), tree, ledgerkit)
    assert caught.value.code == "unknown_helper"
    assert "clamp" in caught.value.message


async def test_open_ended_requests_get_guidance_when_no_model_is_configured(
    tree: Path, ledgerkit: IndexBuild
) -> None:
    with pytest.raises(PlannerError) as caught:
        await plan(TaskSpec("Improve", "Make invoices prettier"), tree, ledgerkit)
    assert caught.value.code == "unsupported"
    assert "LLM_PROVIDER" in caught.value.message
