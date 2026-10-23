"""What a planner works with and what it returns.

Planners are pure with respect to the database: the service layer hands them a `RepoView`
(the working tree of the base commit plus lookups into the index), a `TestHarness` that
runs tests in the sandbox, and a `note` callback that appends to the task's trace.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from codeagent.agent.diffs import FileChange
from codeagent.ai.chat import Usage
from codeagent.ai.sources import CodeSource
from codeagent.sandbox.junit import TestSummary

Note = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    id: uuid.UUID
    name: str
    qualified_name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    parent_name: str | None = None


@dataclass(frozen=True, slots=True)
class RefInfo:
    path: str
    line: int
    kind: str
    source_name: str | None


@dataclass(frozen=True, slots=True)
class FileInfo:
    path: str
    language: str
    is_test: bool


class SymbolIndex(Protocol):
    def by_name(self, name: str) -> list[SymbolInfo]: ...

    def refs_to(self, symbol_id: uuid.UUID) -> list[RefInfo]: ...

    def callees_of(self, symbol_id: uuid.UUID) -> list[SymbolInfo]: ...


@dataclass(slots=True)
class RepoView:
    root: Path
    files: dict[str, FileInfo]
    index: SymbolIndex
    relevant: list[CodeSource] = field(default_factory=list)
    repo_map: str = ""

    def read(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8", errors="replace")

    def exists(self, path: str) -> bool:
        return path in self.files or (self.root / path).is_file()


@dataclass(frozen=True, slots=True)
class TaskSpec:
    title: str
    description: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}".strip()


@dataclass(frozen=True, slots=True)
class PlanStep:
    title: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class HarnessResult:
    """A test run on a changed tree. `run_id` is set when it was stored as a test run."""

    outcome: str  # passed | failed | error | timed_out
    summary: TestSummary | None
    log_tail: str
    run_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    """One whole-file variant to probe, with a human description of what changed."""

    path: str
    content: str
    description: str


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    index: int
    targeted_passed: bool
    full_passed: bool | None


class TestHarness(Protocol):
    baseline: HarnessResult | None

    async def run(self, changes: list[FileChange], *, purpose: str) -> HarnessResult: ...

    async def probe(self, candidates: list[Candidate], tests: list[str]) -> list[ProbeOutcome]: ...


@dataclass(slots=True)
class PlanResult:
    skill: str
    summary: str
    plan: list[PlanStep]
    rationale: str
    changes: list[FileChange]
    usage: Usage = field(default_factory=Usage)
    # A run the planner already made on exactly these changes (the model planner's last
    # iteration); the runner then stores it instead of running the suite again.
    verification: HarnessResult | None = None


class PlannerError(Exception):
    """The planner cannot produce a change. The message is shown to the requester."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Planner(Protocol):
    label: str

    async def plan(
        self, task: TaskSpec, view: RepoView, harness: TestHarness, note: Note
    ) -> PlanResult: ...
