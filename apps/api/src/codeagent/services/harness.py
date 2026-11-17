"""What the agent's planners run against: the index in the database and tests in the sandbox."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anyio
import orjson

from codeagent.agent.diffs import FileChange
from codeagent.agent.probe_driver import CANDIDATES_PATH, DRIVER, DRIVER_PATH, RESULTS_PATH
from codeagent.agent.types import Candidate, HarnessResult, ProbeOutcome, RefInfo, SymbolInfo
from codeagent.core.logging import get_logger
from codeagent.integrations import git
from codeagent.models import Repository, Task, TestRun
from codeagent.models.enums import RunStatus, RunTrigger
from codeagent.repositories.index import IndexRepository, SymbolRow
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.repositories.workspaces import WorkspaceRepository
from codeagent.sandbox import Limits, SandboxSpec
from codeagent.services.container import Container
from codeagent.services.test_runs import Outcome, execute, limits_for, record
from codeagent.services.worktree import copy_tree

log = get_logger("codeagent.harness")


def _info(row: SymbolRow) -> SymbolInfo:
    return SymbolInfo(
        id=row.id,
        name=row.name,
        qualified_name=row.qualified_name,
        kind=row.kind,
        path=row.path,
        start_line=row.start_line,
        end_line=row.end_line,
        parent_name=row.parent_name,
    )


class DbSymbolIndex:
    """The base snapshot's index, one short session per lookup (agent runs are long)."""

    def __init__(self, container: Container, snapshot_id: uuid.UUID) -> None:
        self.c = container
        self.snapshot_id = snapshot_id

    async def by_name(self, name: str) -> list[SymbolInfo]:
        async with self.c.db.session() as session:
            rows = await IndexRepository(session).symbols_named([self.snapshot_id], [name])
        return [_info(row) for row in rows]

    async def refs_to(self, symbol_id: uuid.UUID) -> list[RefInfo]:
        async with self.c.db.session() as session:
            edges = await IndexRepository(session).incoming(symbol_id, limit=2000)
        return [RefInfo(e.path, e.line, e.kind, e.name) for e in edges]

    async def callees_of(self, symbol_id: uuid.UUID) -> list[SymbolInfo]:
        async with self.c.db.session() as session:
            index = IndexRepository(session)
            edges = await index.outgoing(symbol_id, limit=100)
            rows = await index.symbols_by_id([e.symbol_id for e in edges if e.symbol_id])
        return [_info(row) for row in rows]


def write_changes(root: Path, changes: list[FileChange]) -> None:
    for change in changes:
        target = root / change.path
        if change.new is None:
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.new, encoding="utf-8")


class SandboxHarness:
    """Runs tests for one agent run and stores each run against the task."""

    def __init__(
        self,
        container: Container,
        *,
        task: Task,
        repository: Repository,
        base_tree: Path,
        command: str | None,
    ) -> None:
        self.c = container
        self.task = task
        self.repository = repository
        self.base_tree = base_tree
        self.command = command
        self.limits: Limits = limits_for(container.settings, repository)
        self.baseline: HarnessResult | None = None

    async def _stored(
        self, trigger: RunTrigger, outcome: Outcome | None, error: str | None = None
    ) -> uuid.UUID:
        async with self.c.db.session() as session:
            number = await WorkspaceRepository(session).next_run_number(self.task.workspace_id)
            now = datetime.now(UTC)
            run = await TestRunRepository(session).add(
                TestRun(
                    workspace_id=self.task.workspace_id,
                    repository_id=self.repository.id,
                    number=number,
                    snapshot_id=self.task.base_snapshot_id,
                    task_id=self.task.id,
                    trigger=trigger.value,
                    status=RunStatus.RUNNING.value,
                    commit_sha=self.task.base_commit,
                    command=self.command or "",
                    limits=self.limits.public(),
                    created_by=self.task.created_by,
                    started_at=now,
                )
            )
            if outcome is not None:
                await record(self.c, session, run, outcome)
            else:
                run.status = RunStatus.ERROR.value
                run.error = error
                run.finished_at = now
            await session.commit()
            return run.id

    def _result(self, outcome: Outcome, run_id: uuid.UUID | None) -> HarnessResult:
        return HarnessResult(
            outcome=outcome.status.value,
            summary=outcome.summary,
            log_tail=outcome.result.log[-8000:],
            run_id=run_id,
        )

    async def run_baseline(self) -> HarnessResult | None:
        if not self.command:
            return None
        outcome = await execute(
            self.c, self.base_tree, self.command, self.limits, f"task-{self.task.number}-base"
        )
        run_id = await self._stored(RunTrigger.AGENT_BASELINE, outcome)
        self.baseline = self._result(outcome, run_id)
        return self.baseline

    async def run(self, changes: list[FileChange], *, purpose: str) -> HarnessResult:
        if not self.command:
            return HarnessResult(outcome="skipped", summary=None, log_tail="", run_id=None)
        with git.scratch_dir("verify") as scratch:
            tree = Path(scratch) / "tree"
            await anyio.to_thread.run_sync(copy_tree, self.base_tree, tree)
            await anyio.to_thread.run_sync(write_changes, tree, changes)
            outcome = await execute(
                self.c, tree, self.command, self.limits, f"task-{self.task.number}-{purpose}"
            )
        run_id = await self._stored(RunTrigger.AGENT_VERIFY, outcome)
        return self._result(outcome, run_id)

    async def probe(self, candidates: list[Candidate], tests: list[str]) -> list[ProbeOutcome]:
        """Try every candidate in one sandbox run (see agent/probe_driver.py)."""
        if not candidates:
            return []
        with git.scratch_dir("probe") as scratch:
            workdir = Path(scratch) / "workspace"
            await anyio.to_thread.run_sync(copy_tree, self.base_tree, workdir)
            spec_file = workdir / CANDIDATES_PATH
            payload = {
                "tests": tests,
                "timeout_s": max(10, self.limits.timeout_s // 2),
                "candidates": [{"path": c.path, "content": c.content} for c in candidates],
            }

            def prepare() -> None:
                spec_file.parent.mkdir(parents=True, exist_ok=True)
                spec_file.write_bytes(orjson.dumps(payload))
                (workdir / DRIVER_PATH).write_text(DRIVER, encoding="utf-8")

            await anyio.to_thread.run_sync(prepare)
            limits = Limits(
                timeout_s=min(self.c.settings.job_timeout_s - 60, self.limits.timeout_s * 4),
                memory_mb=self.limits.memory_mb,
                cpus=self.limits.cpus,
                pids=self.limits.pids,
            )
            sandbox = await self.c.sandbox()
            result = await sandbox.run(
                SandboxSpec(
                    workdir=workdir,
                    command=f"python {DRIVER_PATH}",
                    limits=limits,
                    image=self.c.settings.sandbox_image,
                    outputs=(RESULTS_PATH,),
                    label=f"task-{self.task.number}-probe",
                )
            )
        raw = result.outputs.get(RESULTS_PATH)
        if raw is None:
            log.warning("probe_without_results", error=result.error, log=result.log[-500:])
            return []
        try:
            entries = json.loads(raw)
        except ValueError:
            return []
        return [
            ProbeOutcome(
                int(e["index"]), bool(e["targeted"]), None if e["full"] is None else bool(e["full"])
            )
            for e in entries
        ]
