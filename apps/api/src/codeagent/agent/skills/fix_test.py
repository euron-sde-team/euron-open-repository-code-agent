"""Repair a failing test by searching small, verified changes to the code it exercises.

1. Read the failing tests from the baseline run.
2. Find the functions each failing test calls, through the test's syntax tree and the
   reference graph (direct callees first, then what they call).
3. Enumerate mutations of those functions (see `agent/mutations.py`), best first.
4. Probe them in one sandbox run: a candidate must make the failing tests pass and keep the
   whole suite green. The first that does is the fix.

This is mutation-based program repair in its simplest useful form. It finds the common
one-token bugs (a strict boundary, a reversed comparison, an off-by-one constant, the wrong
rounding mode) and it never proposes a change it has not seen pass the tests.
"""

from __future__ import annotations

import ast
import re

from codeagent.agent.diffs import FileChange
from codeagent.agent.mutations import Mutation, mutations
from codeagent.agent.types import (
    Candidate,
    Note,
    PlannerError,
    PlanResult,
    PlanStep,
    RepoView,
    SymbolInfo,
    TaskSpec,
    TestHarness,
)
from codeagent.sandbox.junit import CaseResult

PATTERN = re.compile(
    r"\b(fix|repair|make)\b.*\b(fail(ing|ed|s)?|broken|red)\b.*\btests?\b|\bmake\b.*\btests?\b.*\bpass\b|"
    r"\bfix\b.*\btest_\w+",
    re.IGNORECASE | re.DOTALL,
)
_HINT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
MAX_FILE_CHARS = 200_000


def matches(task: TaskSpec) -> bool:
    return bool(PATTERN.search(task.text))


def node_id(case: CaseResult) -> str | None:
    if not case.file:
        return None
    module = case.file.removesuffix(".py").replace("/", ".")
    classes = case.classname.removeprefix(module).strip(".")
    parts = [case.file, *(part for part in classes.split(".") if part), case.name]
    return "::".join(parts)


def _test_calls(source: str, test_name: str) -> list[str]:
    base = test_name.split("[", 1)[0]
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == base:
            names: list[str] = []
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        names.append(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        names.append(child.func.attr)
            return list(dict.fromkeys(names))
    return []


def _targets(view: RepoView, failing: list[CaseResult]) -> list[tuple[SymbolInfo, int]]:
    """Non-test functions the failing tests reach: (symbol, distance), nearest first."""
    found: dict[str, tuple[SymbolInfo, int]] = {}
    for case in failing:
        if not case.file or not view.exists(case.file):
            continue
        for name in _test_calls(view.read(case.file), case.name):
            for symbol in view.index.by_name(name):
                info = view.files.get(symbol.path)
                if info is None or info.is_test or info.language != "Python":
                    continue
                if symbol.kind not in {"function", "method"}:
                    # Constructing a class runs its methods: probe those instead.
                    continue
                found.setdefault(str(symbol.id), (symbol, 0))
    for symbol, _ in list(found.values()):
        for callee in view.index.callees_of(symbol.id):
            info = view.files.get(callee.path)
            if info is not None and not info.is_test and callee.kind in {"function", "method"}:
                found.setdefault(str(callee.id), (callee, 1))
    return sorted(found.values(), key=lambda item: item[1])


def _describe_failure(case: CaseResult) -> str:
    first = case.message.strip().splitlines()[0] if case.message.strip() else "it failed"
    return first[:240]


async def fix_failing_test(
    task: TaskSpec, view: RepoView, harness: TestHarness, note: Note, *, budget: int
) -> PlanResult:
    baseline = harness.baseline
    if baseline is None or baseline.summary is None:
        raise PlannerError(
            "no_results",
            "The baseline test run produced no per-test results, so there is no failing test "
            "to work from.",
        )
    failing = [c for c in baseline.summary.cases if c.status in {"failed", "error"}]
    mentioned = [c for c in failing if c.name.split("[", 1)[0] in task.text]
    failing = mentioned or failing
    if not failing:
        raise PlannerError(
            "nothing_to_fix",
            f"All {baseline.summary.total} tests pass on the base commit; "
            "there is no failing test to fix.",
        )
    test_ids = [tid for case in failing if (tid := node_id(case))]
    await note(
        f"{len(failing)} failing test(s): " + ", ".join(f"`{c.name}`" for c in failing[:4]) + "."
    )
    targets = _targets(view, failing)
    if not targets:
        raise PlannerError(
            "no_targets", "Could not find the code the failing test calls in the index."
        )
    await note(
        "Searching "
        + ", ".join(f"`{s.qualified_name}`" for s, _ in targets[:5])
        + " for the fault."
    )

    hints = {match for case in failing for match in _HINT.findall(case.message)}
    ranked: list[tuple[float, SymbolInfo, Mutation]] = []
    sources: dict[str, str] = {}
    for symbol, distance in targets:
        if symbol.path not in sources:
            sources[symbol.path] = view.read(symbol.path)
        source = sources[symbol.path]
        if len(source) > MAX_FILE_CHARS:
            continue
        try:
            found = mutations(source, symbol.start_line, symbol.end_line, hints)
        except SyntaxError:
            continue
        ranked.extend((m.priority + distance, symbol, m) for m in found)
    ranked.sort(key=lambda item: item[0])
    ranked = ranked[:budget]
    if not ranked:
        raise PlannerError("no_candidates", "No small change to the called code could be tried.")

    candidates = [
        Candidate(
            symbol.path,
            mutation.apply(sources[symbol.path]),
            mutation.summary(sources[symbol.path]),
        )
        for _, symbol, mutation in ranked
    ]
    await note(f"Probing {len(candidates)} candidate change(s) in the sandbox.")
    outcomes = await harness.probe(candidates, test_ids)
    winner = next((o for o in outcomes if o.targeted_passed and o.full_passed), None)
    if winner is None:
        partial = sum(1 for o in outcomes if o.targeted_passed)
        detail = f" {partial} of them fixed the test but broke others." if partial else ""
        raise PlannerError(
            "no_fix_found",
            f"Tried {len(outcomes)} small change(s) to "
            + ", ".join(f"`{s.qualified_name}`" for s, _ in targets[:4])
            + f"; none made `{failing[0].name}` pass without breaking other tests.{detail} "
            f"The failure: {_describe_failure(failing[0])}",
        )
    _, symbol, mutation = ranked[winner.index]
    original = sources[symbol.path]
    fixed = mutation.apply(original)
    await note(f"Candidate {winner.index + 1} passes the failing test and the whole suite.")
    test_names = ", ".join(f"`{c.name}`" for c in failing[:3])
    rationale = (
        f"{test_names} failed on the base commit: {_describe_failure(failing[0])}. "
        f"The test exercises `{symbol.qualified_name}` in `{symbol.path}`. Changing "
        f"{mutation.summary(original)} makes the failing test pass, and the full suite passes "
        f"with it. {winner.index + 1} of {len(candidates)} ranked candidate change(s) were tried "
        "in the sandbox before this one was accepted; the others did not fix the test."
    )
    return PlanResult(
        skill="fix_test",
        summary=f"Fix {failing[0].name}",
        plan=[
            PlanStep("Read the failure", _describe_failure(failing[0])),
            PlanStep(
                "Trace the code under test",
                ", ".join(f"`{s.qualified_name}`" for s, _ in targets[:4]),
            ),
            PlanStep(
                "Search candidate fixes",
                f"{len(candidates)} ranked mutation(s), probed in one sandbox run",
            ),
            PlanStep("Accept the first verified fix", mutation.summary(original)),
        ],
        rationale=rationale,
        changes=[FileChange(symbol.path, original, fixed)],
    )
