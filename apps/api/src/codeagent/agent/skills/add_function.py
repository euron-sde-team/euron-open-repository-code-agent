"""Add a catalogued helper function to a Python package, with tests.

The task names the function (and optionally the module): "Add a `round_half_up` helper
to ledgerkit/money.py with tests". The implementation and its tests come from the helper
catalog; the skill decides where they go, adds imports and `__all__`, and turns any
`Examples:` lines in the description (`name(args) == result`) into extra test cases.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import PurePosixPath

from codeagent.agent import catalog, pyedit
from codeagent.agent.diffs import FileChange
from codeagent.agent.types import Note, PlannerError, PlanResult, PlanStep, RepoView, TaskSpec
from codeagent.codeintel.symbols.python import module_name

_VERB = re.compile(r"\b(add|create|write|implement|introduce)\b", re.IGNORECASE)
_BACKTICKED = re.compile(r"`([A-Za-z_][\w./]*)`")
_NAMED = re.compile(
    r"\b(?:add|create|write|implement|introduce)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?"
    r"(?:function|helper|utility|method)\s+(?:called\s+|named\s+)?(?P<name>[A-Za-z_]\w*)",
    re.IGNORECASE,
)
_TARGET = re.compile(
    r"\b(?:to|in|into|inside)\s+`?(?P<target>[\w./-]+\.py|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)`?",
    re.IGNORECASE,
)
_EXAMPLE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?P<call>[A-Za-z_]\w*\(.*\))\s*(?:==|->|=>)\s*(?P<expected>[^`]+?)`?\s*$"
)
_NOT_NAMES = frozenset({"tests", "test", "function", "helper", "a", "an", "the", "new", "support"})


def parse_name(task: TaskSpec) -> str | None:
    text = task.text
    if not _VERB.search(text):
        return None
    for candidate in _BACKTICKED.findall(text):
        if "/" not in candidate and "." not in candidate:
            return str(candidate)
    match = _NAMED.search(text)
    if match and match.group("name").lower() not in _NOT_NAMES:
        return match.group("name")
    return None


def parse_target(task: TaskSpec) -> str | None:
    for match in _TARGET.finditer(task.text):
        target = match.group("target").strip("`")
        if target.endswith(".py") or "." in target:
            return target
    return None


def parse_examples(description: str, name: str) -> list[str]:
    """`name(args) == expected` assertions from the description, validated as expressions."""
    examples = []
    for line in description.splitlines():
        match = _EXAMPLE.match(line)
        if not match or not match.group("call").startswith(f"{name}("):
            continue
        expression = f"{match.group('call')} == {match.group('expected').strip()}"
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError:
            continue
        if isinstance(tree.body, ast.Compare):
            examples.append(expression)
    return examples


def _package_files(view: RepoView) -> list[str]:
    return [
        path
        for path, info in view.files.items()
        if info.language == "Python"
        and not info.is_test
        and not path.startswith(("docs/", "scripts/"))
    ]


def _resolve_target(view: RepoView, target: str | None) -> str:
    python_files = _package_files(view)
    if target:
        if target.endswith(".py"):
            return target.removeprefix("./")
        for path in python_files:
            if module_name(path) == target:
                return path
        return target.replace(".", "/") + ".py"
    # The package with the most modules gets a utils module.
    packages = Counter(
        str(PurePosixPath(path).parent)
        for path in python_files
        if PurePosixPath(path).name == "__init__.py"
        or (PurePosixPath(path).parent / "__init__.py").as_posix() in view.files
    )
    if not packages:
        raise PlannerError(
            "no_package",
            "No Python package was found to add the function to. Name the target module.",
        )
    package = packages.most_common(1)[0][0]
    return f"{package}/utils.py"


def _tests_dir(view: RepoView) -> str:
    for candidate in ("tests", "test"):
        if any(path.startswith(f"{candidate}/") for path in view.files):
            return candidate
    return "tests"


def _test_module(
    module: str, name: str, helper: catalog.Helper, examples: list[str]
) -> tuple[list[str], str]:
    imports = [f"from {module} import {name}", *helper.test_imports]
    body = helper.render_tests(name)
    for index, expression in enumerate(examples, start=1):
        body += f"\n\ndef test_{name}_example_{index}():\n    assert {expression}\n"
    return imports, body


async def add_function(task: TaskSpec, view: RepoView, note: Note) -> PlanResult:
    name = parse_name(task)
    if name is None:
        raise PlannerError(
            "unrecognised", "Name the function to add, for example: add `slugify` to app/text.py."
        )
    helper = catalog.find(name)
    if helper is None:
        known = ", ".join(f"`{n}`" for n in catalog.names())
        raise PlannerError(
            "unknown_helper",
            f"The offline planner has no implementation for `{name}`. It can add {known}. "
            "Configure a model provider (LLM_PROVIDER) for open-ended functions.",
        )
    path = _resolve_target(view, parse_target(task))
    if not path.endswith(".py"):
        raise PlannerError(
            "unsupported_language", "The offline planner adds functions to Python modules."
        )
    existing = view.read(path) if view.exists(path) else None
    if existing is not None:
        try:
            if pyedit.defines(existing, name):
                raise PlannerError("already_exists", f"`{name}` is already defined in `{path}`.")
        except SyntaxError as exc:
            raise PlannerError("unparseable", f"`{path}` does not parse: {exc.msg}") from exc
    await note(f"Adding `{name}` ({helper.summary.rstrip('.').lower()}) to `{path}`.")

    module_source = existing or f'"""{helper.summary}"""\n'
    module_source = pyedit.insert_imports(module_source, list(helper.imports))
    module_source = pyedit.append_definition(module_source, helper.render_source(name))
    module_source = pyedit.add_to_all(module_source, name)
    changes = [FileChange(path, existing, module_source)]

    module = module_name(path)
    examples = parse_examples(task.description, name)
    tests_dir = _tests_dir(view)
    stem = PurePosixPath(path).stem
    test_path = (
        f"{tests_dir}/test_{stem}.py"
        if stem not in {"__init__", "utils"}
        else f"{tests_dir}/test_{name}.py"
    )
    imports, body = _test_module(module, name, helper, examples)
    current_tests = view.read(test_path) if view.exists(test_path) else None
    test_source = current_tests or f'"""Tests for {module}.{name}."""\n'
    test_source = pyedit.insert_imports(test_source, imports)
    test_source = pyedit.append_definition(test_source, body)
    changes.append(FileChange(test_path, current_tests, test_source))
    test_count = body.count("\ndef test_") + (1 if body.startswith("def test_") else 0)
    await note(
        f"Wrote {test_count} test(s) in `{test_path}`"
        + (f", {len(examples)} from the examples." if examples else ".")
    )

    where = "a new module" if existing is None else f"`{path}`"
    rationale = (
        f"Adds `{name}` to {where}: {helper.summary[0].lower()}{helper.summary[1:]} "
        f"The implementation comes from CodeAgent's catalog of reviewed helpers; it is typed, "
        f"documented and exported through `__all__` where the module declares one. "
        f"{test_count} test(s) in `{test_path}` cover the normal cases and the edge cases"
        + (f", including {len(examples)} example(s) from the task description" if examples else "")
        + ". The suite runs in the sandbox before and after the change."
    )
    return PlanResult(
        skill="add_function",
        summary=f"Add `{name}` with tests",
        plan=[
            PlanStep("Choose the module", f"`{path}`" + (" (new)" if existing is None else "")),
            PlanStep(
                "Add the function",
                f"`{name}` with its imports"
                + (" and `__all__` entry" if "__all__" in module_source else ""),
            ),
            PlanStep("Write tests", f"{test_count} test(s) in `{test_path}`"),
            PlanStep("Run the tests", "before and after the change, in the sandbox"),
        ],
        rationale=rationale,
        changes=changes,
    )
