"""Sandboxed test runs: queued from the UI, the API or a patch; executed by the worker.

The sandbox always works on a copy of the tree without `.git`. The result keeps per-test
outcomes (from JUnit XML), the last 64 KB of the log inline and the full log in S3.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.core import metrics
from codeagent.core.config import Settings
from codeagent.core.errors import ConflictError, NotFoundError, UnprocessableError
from codeagent.core.logging import get_logger
from codeagent.integrations import git
from codeagent.integrations.queue import Job, JobType
from codeagent.integrations.storage import test_log_key
from codeagent.models import Patch, Repository, TestRun, Workspace
from codeagent.models.enums import RunStatus, RunTrigger
from codeagent.repositories.repos import ReposRepository, SnapshotRepository
from codeagent.repositories.tasks import PatchRepository
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.repositories.workspaces import WorkspaceRepository
from codeagent.sandbox import Limits, SandboxResult, SandboxSpec, default_limits
from codeagent.sandbox.junit import TestSummary, parse_junit, parse_pytest_summary
from codeagent.sandbox.types import prepare_command
from codeagent.schemas.repositories import RepositorySettings
from codeagent.services.container import Container
from codeagent.services.principal import Principal
from codeagent.services.worktree import checkout, copy_tree

log = get_logger("codeagent.test_runs")
LOG_TAIL_BYTES = 64 * 1024
MAX_RESULTS = 1000
MAX_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class Outcome:
    status: RunStatus
    result: SandboxResult
    summary: TestSummary | None


def test_command(repository: Repository) -> str | None:
    settings = RepositorySettings.model_validate(repository.settings or {})
    command = (settings.test_command or "").strip()
    return prepare_command(command) if command else None


def limits_for(settings: Settings, repository: Repository) -> Limits:
    """The repository's limits, never above the deployment's."""
    base = default_limits(settings)
    own = RepositorySettings.model_validate(repository.settings or {})
    return Limits(
        timeout_s=min(own.test_timeout_s or base.timeout_s, base.timeout_s),
        memory_mb=min(own.memory_mb or base.memory_mb, base.memory_mb),
        cpus=base.cpus,
        pids=base.pids,
    )


def classify(result: SandboxResult, summary: TestSummary | None) -> RunStatus:
    if result.error:
        return RunStatus.ERROR
    if result.timed_out:
        return RunStatus.TIMED_OUT
    if result.exit_code == 0 and (summary is None or summary.failed + summary.errors == 0):
        return RunStatus.PASSED
    if summary is not None and summary.total == 0 and result.exit_code == 5:
        return RunStatus.ERROR  # pytest: no tests were collected
    return RunStatus.FAILED


async def execute(
    container: Container, tree: Path, command: str, limits: Limits, label: str
) -> Outcome:
    """Run `command` on a disposable copy of `tree` in the sandbox."""
    with git.scratch_dir("run") as scratch:
        workdir = Path(scratch) / "workspace"
        await anyio.to_thread.run_sync(copy_tree, tree, workdir)
        sandbox = await container.sandbox()
        result = await sandbox.run(
            SandboxSpec(
                workdir=workdir,
                command=command,
                limits=limits,
                image=container.settings.sandbox_image,
                label=label,
            )
        )
    summary = parse_junit(result.junit_xml) if result.junit_xml else None
    if summary is None and not result.error:
        summary = parse_pytest_summary(result.log)
    return Outcome(classify(result, summary), result, summary)


async def record(
    container: Container, session: AsyncSession, run: TestRun, outcome: Outcome
) -> None:
    """Store an outcome on its run row (the caller commits)."""
    result, summary = outcome.result, outcome.summary
    log_bytes = result.log.encode()
    if len(log_bytes) > LOG_TAIL_BYTES:
        key = test_log_key(run.workspace_id, run.id)
        try:
            await container.storage.put(key, log_bytes, "text/plain; charset=utf-8")
            run.log_key = key
        except Exception:
            log.warning("test_log_upload_failed", run_id=str(run.id))
    run.status = outcome.status
    run.backend = result.backend
    run.image = result.image
    run.exit_code = result.exit_code
    run.duration_ms = result.duration_ms
    run.error = (
        result.error
        or ("The run was stopped at its time limit." if result.timed_out else None)
        or ("The run ran out of memory." if result.oom_killed else None)
    )
    run.log_tail = log_bytes[-LOG_TAIL_BYTES:].decode("utf-8", "replace")
    run.log_truncated = result.log_truncated or len(log_bytes) > LOG_TAIL_BYTES
    if summary is not None:
        run.total, run.passed, run.failed = summary.total, summary.passed, summary.failed
        run.errors, run.skipped = summary.errors, summary.skipped
        run.results = [case.public() for case in summary.cases[:MAX_RESULTS]]
    run.finished_at = datetime.now(UTC)
    metrics.JOBS.labels(JobType.RUN_TESTS.value, outcome.status.value).inc()


class TestRunService:
    __test__ = False

    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.runs = TestRunRepository(session)

    async def _new_run(
        self,
        workspace: Workspace,
        repository: Repository,
        *,
        trigger: RunTrigger,
        commit_sha: str | None,
        snapshot_id: uuid.UUID | None,
        principal_user: uuid.UUID | None,
        task_id: uuid.UUID | None = None,
        patch_id: uuid.UUID | None = None,
        status: RunStatus = RunStatus.QUEUED,
    ) -> TestRun:
        command = test_command(repository)
        if command is None:
            raise UnprocessableError(
                "This repository has no test command. Set one in the repository settings.",
                code="no_test_command",
            )
        number = await WorkspaceRepository(self.session).next_run_number(workspace.id)
        return await self.runs.add(
            TestRun(
                workspace_id=workspace.id,
                repository_id=repository.id,
                number=number,
                snapshot_id=snapshot_id,
                task_id=task_id,
                patch_id=patch_id,
                trigger=trigger.value,
                status=status.value,
                commit_sha=commit_sha,
                command=command,
                limits=limits_for(self.c.settings, repository).public(),
                created_by=principal_user,
            )
        )

    async def start(
        self, workspace: Workspace, principal: Principal, repository: Repository
    ) -> TestRun:
        if repository.current_snapshot_id is None:
            raise ConflictError("The repository has no index yet.", code="not_indexed")
        current = await SnapshotRepository(self.session).get(
            workspace.id, repository.current_snapshot_id
        )
        run = await self._new_run(
            workspace,
            repository,
            trigger=RunTrigger.MANUAL,
            commit_sha=current.commit_sha if current else None,
            snapshot_id=repository.current_snapshot_id,
            principal_user=principal.user_id,
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job(JobType.RUN_TESTS, workspace.id, run.id))
        return run

    async def start_for_patch(
        self, workspace: Workspace, principal: Principal, repository: Repository, patch: Patch
    ) -> TestRun:
        run = await self._new_run(
            workspace,
            repository,
            trigger=RunTrigger.PATCH,
            commit_sha=patch.base_commit,
            snapshot_id=None,
            principal_user=principal.user_id,
            task_id=patch.task_id,
            patch_id=patch.id,
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job(JobType.RUN_TESTS, workspace.id, run.id))
        return run

    async def get(self, workspace_id: uuid.UUID, ref: str) -> TestRun:
        run = None
        if ref.isdigit():
            run = await self.runs.by_number(workspace_id, int(ref))
        else:
            try:
                run = await self.runs.get(workspace_id, uuid.UUID(ref))
            except ValueError:
                run = None
        if run is None:
            raise NotFoundError("Test run not found.")
        return run

    async def full_log(self, run: TestRun) -> str:
        if run.log_key:
            try:
                return (await self.c.storage.get(run.log_key)).decode("utf-8", "replace")
            except NotFoundError:
                pass
        return run.log_tail

    async def process(self, job: Job) -> bool:
        """Execute one queued run (manual or patch). Agent runs execute inside their task."""
        async with self.c.db.session() as session:
            runs = TestRunRepository(session)
            run = await runs.get_for_update(job.workspace_id, job.target_id)
            if run is None or RunStatus(run.status).finished:
                return True
            repository = await ReposRepository(session).get(job.workspace_id, run.repository_id)
            patch = (
                await PatchRepository(session).get(job.workspace_id, run.patch_id)
                if run.patch_id
                else None
            )
            if repository is None:
                return True
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC)
            run.attempts += 1
            await session.commit()
            limits = limits_for(self.c.settings, repository)
            command, commit, label = run.command, run.commit_sha, f"run-{run.number}"
            diff = patch.diff if patch is not None else None
            session.expunge_all()

        try:
            async with checkout(self.c.storage, repository, commit) as tree:
                if diff:
                    await git.apply(tree, diff)
                outcome = await execute(self.c, tree, command, limits, label)
        except Exception as exc:  # the run records the failure; the job itself is done
            log.exception("test_run_failed", run_id=str(job.target_id))
            message = getattr(exc, "message", None) or "The run could not be started."
            async with self.c.db.session() as session:
                await TestRunRepository(session).mark(
                    job.target_id,
                    status=RunStatus.ERROR,
                    error=message,
                    finished_at=datetime.now(UTC),
                )
                await session.commit()
            return True

        async with self.c.db.session() as session:
            run = await TestRunRepository(session).get_for_update(job.workspace_id, job.target_id)
            if run is None:
                return True
            await record(self.c, session, run, outcome)
            await session.commit()
        return True

    async def reap_stale(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=self.c.settings.stale_job_minutes)
        resend: list[Job] = []
        async with self.c.db.session() as session:
            stale = await TestRunRepository(session).unfinished_before(cutoff)
            for run in stale:
                if run.attempts >= MAX_ATTEMPTS:
                    run.status = RunStatus.ERROR
                    run.error = "The run did not finish after several attempts."
                    run.finished_at = datetime.now(UTC)
                else:
                    run.status = RunStatus.QUEUED
                    run.updated_at = datetime.now(UTC)
                    resend.append(Job(JobType.RUN_TESTS, run.workspace_id, run.id))
            await session.commit()
        for job in resend:
            await self.c.queue.enqueue(job)
        return len(stale)
