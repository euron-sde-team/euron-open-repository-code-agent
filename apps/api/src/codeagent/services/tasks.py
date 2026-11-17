"""Tasks: describe a change, let the agent propose a patch, track it through review.

The agent run (`run`, in the worker) materializes the base commit, runs the baseline
tests, asks the planner for a change, checks that the patch applies to the base commit,
verifies it in the sandbox and stores it as a new revision for review. The agent never
writes to the repository: only an approved patch, applied by a maintainer, does.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.agent.diffs import build_patch, stats
from codeagent.agent.planners import ModelPlanner
from codeagent.agent.types import FileInfo, Planner, PlannerError, PlanResult, RepoView, TaskSpec
from codeagent.codeintel.languages import detect_language
from codeagent.core import metrics
from codeagent.core.errors import ConflictError, NotFoundError
from codeagent.core.logging import get_logger
from codeagent.integrations import git
from codeagent.integrations.queue import Job, JobType
from codeagent.models import Patch, PatchFile, Repository, Task, Workspace
from codeagent.models.enums import PatchStatus, Role, TaskStatus
from codeagent.repositories.index import IndexRepository
from codeagent.repositories.repos import ReposRepository, SearchScope, SnapshotRepository
from codeagent.repositories.tasks import PatchRepository, TaskRepository
from codeagent.repositories.workspaces import WorkspaceRepository
from codeagent.schemas.workspaces import WorkspaceSettings
from codeagent.services import audit
from codeagent.services.container import Container
from codeagent.services.harness import DbSymbolIndex, SandboxHarness
from codeagent.services.principal import Principal
from codeagent.services.retrieval import RetrievalService
from codeagent.services.test_runs import test_command
from codeagent.services.worktree import checkout

log = get_logger("codeagent.tasks")
RETRYABLE = frozenset(
    {TaskStatus.FAILED, TaskStatus.REJECTED, TaskStatus.AWAITING_REVIEW, TaskStatus.CANCELLED}
)
MAX_ATTEMPTS = 3
REPO_MAP_SYMBOLS = 300


def can_decide(
    task: Task, patch: Patch | None, principal: Principal, role: Role, workspace: Workspace
) -> bool:
    if patch is None or patch.status != PatchStatus.PROPOSED or not role.allows(Role.MAINTAINER):
        return False
    settings = WorkspaceSettings.model_validate(workspace.settings or {})
    return not (settings.require_independent_review and task.created_by == principal.user_id)


class TaskService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.tasks = TaskRepository(session)
        self.patches = PatchRepository(session)

    async def create(
        self,
        workspace: Workspace,
        principal: Principal,
        repository: Repository,
        title: str,
        description: str,
    ) -> Task:
        if repository.current_snapshot_id is None:
            raise ConflictError(
                "The repository has no index yet. Wait for indexing to finish.", code="not_indexed"
            )
        snapshot = await SnapshotRepository(self.session).get(
            workspace.id, repository.current_snapshot_id
        )
        number = await WorkspaceRepository(self.session).next_task_number(workspace.id)
        task = await self.tasks.add(
            Task(
                workspace_id=workspace.id,
                repository_id=repository.id,
                number=number,
                title=title.strip(),
                description=description.strip(),
                status=TaskStatus.QUEUED,
                base_snapshot_id=repository.current_snapshot_id,
                base_commit=snapshot.commit_sha if snapshot else None,
                trace=[_event("Queued for the agent.", "info")],
                created_by=principal.user_id,
            )
        )
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="task.created",
            target_type="task",
            target_id=task.id,
            details={"number": number, "title": task.title, "repository": repository.slug},
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job(JobType.RUN_TASK, workspace.id, task.id))
        return task

    async def get(self, workspace_id: uuid.UUID, ref: str) -> Task:
        task = None
        if ref.isdigit():
            task = await self.tasks.by_number(workspace_id, int(ref))
        else:
            try:
                task = await self.tasks.get(workspace_id, uuid.UUID(ref))
            except ValueError:
                task = None
        if task is None:
            raise NotFoundError("Task not found.")
        return task

    async def retry(
        self, workspace: Workspace, principal: Principal, task: Task, description: str | None
    ) -> Task:
        if TaskStatus(task.status) not in RETRYABLE:
            raise ConflictError(
                "Only failed, rejected, cancelled or proposed tasks can be retried."
            )
        repository = await ReposRepository(self.session).get(workspace.id, task.repository_id)
        if repository is None or repository.current_snapshot_id is None:
            raise ConflictError("The repository has no index.", code="not_indexed")
        snapshot = await SnapshotRepository(self.session).get(
            workspace.id, repository.current_snapshot_id
        )
        if description is not None:
            task.description = description.strip()
        task.status = TaskStatus.QUEUED
        task.error = task.error_code = None
        task.attempts = 0
        task.base_snapshot_id = repository.current_snapshot_id
        task.base_commit = snapshot.commit_sha if snapshot else task.base_commit
        await self.tasks.append_trace(
            task.id, _event("Retry requested: queued for a new revision.", "info")
        )
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="task.retried",
            target_type="task",
            target_id=task.id,
            details={"number": task.number},
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job(JobType.RUN_TASK, workspace.id, task.id))
        return task

    async def cancel(self, workspace: Workspace, principal: Principal, task: Task) -> Task:
        if task.status != TaskStatus.QUEUED:
            raise ConflictError("Only a queued task can be cancelled.")
        task.status = TaskStatus.CANCELLED
        task.finished_at = datetime.now(UTC)
        await self.tasks.append_trace(task.id, _event("Cancelled.", "info"))
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="task.cancelled",
            target_type="task",
            target_id=task.id,
            details={"number": task.number},
        )
        await self.session.commit()
        return task

    # The agent run (worker).

    async def _note(self, task_id: uuid.UUID, message: str, kind: str = "info") -> None:
        async with self.c.db.session() as session:
            await TaskRepository(session).append_trace(task_id, _event(message, kind))
            await session.commit()

    async def _fail(self, task: Task, code: str, message: str) -> None:
        metrics.AGENT_RUNS.labels(task.skill or "unknown", "failed").inc()
        async with self.c.db.session() as session:
            tasks = TaskRepository(session)
            current = await tasks.get_for_update(task.workspace_id, task.id)
            if current is None:
                return
            current.status = TaskStatus.FAILED
            current.error_code = code
            current.error = message
            current.finished_at = datetime.now(UTC)
            await tasks.append_trace(task.id, _event(message, "error"))
            await session.commit()

    def _planner(self, workspace: Workspace) -> Planner:
        settings = WorkspaceSettings.model_validate(workspace.settings or {})
        return self.c.planner if settings.agent_mode == "auto" else self.c.local_planner

    async def _view(
        self, task: Task, repository: Repository, planner: Planner, tree: Path
    ) -> RepoView:
        snapshot_id = task.base_snapshot_id
        if snapshot_id is None:
            raise PlannerError("no_index", "The task's base snapshot was pruned; retry the task.")
        async with self.c.db.session() as session:
            entries = await IndexRepository(session).files(snapshot_id)
            view = RepoView(
                root=tree,
                files={e.path: FileInfo(e.path, e.language, e.is_test) for e in entries},
                index=DbSymbolIndex(self.c, snapshot_id),
            )
            if isinstance(planner, ModelPlanner):
                # Retrieval reads the task's base snapshot, which a later sync may have
                # replaced as the repository's current one.
                scope = SearchScope(repository.id, repository.slug, repository.name, snapshot_id)
                view.relevant, _ = await RetrievalService(self.c, session).chunks(
                    task.workspace_id, [scope], f"{task.title}\n{task.description}", limit=10
                )
                view.repo_map = await self._repo_map(session, snapshot_id)
        return view

    async def _repo_map(self, session: AsyncSession, snapshot_id: uuid.UUID) -> str:
        """Paths with their top-level symbols, most referenced first: the model's map."""
        entries = await IndexRepository(session).files(snapshot_id)
        rows = await IndexRepository(session).top_symbols(snapshot_id, REPO_MAP_SYMBOLS)
        by_path: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            by_path[row.path].append(row.signature or row.name)
        lines = []
        for entry in entries:
            lines.append(entry.path)
            lines.extend(f"    {signature}" for signature in by_path.get(entry.path, [])[:12])
        return "\n".join(lines[:1500])

    async def run(self, job: Job) -> bool:
        async with self.c.db.session() as session:
            tasks = TaskRepository(session)
            task = await tasks.get_for_update(job.workspace_id, job.target_id)
            if task is None or task.status != TaskStatus.QUEUED:
                return True
            workspace = await WorkspaceRepository(session).get(task.workspace_id)
            repository = await ReposRepository(session).get(task.workspace_id, task.repository_id)
            if workspace is None or repository is None:
                return True
            planner = self._planner(workspace)
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(UTC)
            task.finished_at = None
            task.attempts += 1
            task.planner = planner.label
            await tasks.append_trace(
                task.id, _event(f"Started with the {planner.label} planner.", "info")
            )
            await session.commit()
            session.expunge_all()

        started = time.perf_counter()
        settings = WorkspaceSettings.model_validate(workspace.settings or {})
        try:
            result, baseline_id, verify_id, patch_text = await self._execute(
                task, repository, planner, settings
            )
        except PlannerError as exc:
            await self._fail(task, exc.code, exc.message)
            return True
        except git.GitError as exc:
            log.warning("agent_git_failed", task=task.number, detail=exc.detail[-400:])
            await self._fail(task, "patch_not_applicable", exc.message)
            return True
        except TimeoutError:
            await self._fail(task, "timeout", "The agent run took too long and was stopped.")
            return True
        except Exception:
            log.exception("agent_run_failed", task=task.number)
            await self._fail(
                task, "internal_error", "The agent run failed unexpectedly. Retry the task."
            )
            return True
        await self._propose(task, result, patch_text, baseline_id, verify_id, planner.label)
        metrics.AGENT_RUNS.labels(result.skill, "proposed").inc()
        metrics.JOB_DURATION.labels(JobType.RUN_TASK.value).observe(time.perf_counter() - started)
        return True

    async def _execute(
        self, task: Task, repository: Repository, planner: Planner, settings: WorkspaceSettings
    ) -> tuple[PlanResult, uuid.UUID | None, uuid.UUID | None, str]:
        with anyio.fail_after(self.c.settings.job_timeout_s):
            async with checkout(self.c.storage, repository, task.base_commit) as tree:
                command = test_command(repository)
                harness = SandboxHarness(
                    self.c, task=task, repository=repository, base_tree=tree, command=command
                )
                if command and settings.run_baseline_tests:
                    await self._note(task.id, "Running the tests on the base commit.")
                    baseline = await harness.run_baseline()
                    if baseline is not None:
                        await self._note(
                            task.id,
                            _describe_run("Baseline", baseline.outcome, baseline.summary),
                            "test",
                        )
                elif not command:
                    await self._note(
                        task.id, "This repository has no test command, so tests are skipped."
                    )
                view = await self._view(task, repository, planner, tree)

                async def note(message: str) -> None:
                    await self._note(task.id, message)

                result = await planner.plan(
                    TaskSpec(task.title, task.description), view, harness, note
                )
                patch_text = build_patch(result.changes)
                if not patch_text:
                    raise PlannerError("no_changes", "The planner produced no change.")
                await git.apply_check(tree, patch_text)
                await self._note(
                    task.id,
                    f"The patch applies cleanly to {(task.base_commit or 'the base')[:12]}.",
                )
                verification = result.verification
                if verification is None:
                    await self._note(task.id, "Running the tests on the patched tree.")
                    verification = await harness.run(result.changes, purpose="verify")
                if verification.outcome != "skipped":
                    await self._note(
                        task.id,
                        _describe_run("Verification", verification.outcome, verification.summary),
                        "test",
                    )
                baseline_id = harness.baseline.run_id if harness.baseline else None
                return result, baseline_id, verification.run_id, patch_text

    async def _propose(
        self,
        task: Task,
        result: PlanResult,
        patch_text: str,
        baseline_id: uuid.UUID | None,
        verify_id: uuid.UUID | None,
        planner_label: str,
    ) -> None:
        file_stats = stats(result.changes)
        by_path = {s.path: s for s in file_stats}
        async with self.c.db.session() as session:
            tasks, patches = TaskRepository(session), PatchRepository(session)
            current = await tasks.get_for_update(task.workspace_id, task.id)
            if current is None:
                return
            latest = await patches.latest(task.id)
            revision = (latest.revision if latest else 0) + 1
            await patches.supersede_proposed(task.id)
            await patches.add(
                Patch(
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    revision=revision,
                    status=PatchStatus.PROPOSED,
                    summary=result.summary[:300],
                    rationale=result.rationale,
                    plan=[{"title": step.title, "detail": step.detail} for step in result.plan],
                    diff=patch_text,
                    files=[
                        {
                            "path": s.path,
                            "change_type": s.change_type,
                            "additions": s.additions,
                            "deletions": s.deletions,
                        }
                        for s in file_stats
                    ],
                    additions=sum(s.additions for s in file_stats),
                    deletions=sum(s.deletions for s in file_stats),
                    base_commit=task.base_commit,
                    planner=planner_label,
                    skill=result.skill,
                    baseline_run_id=baseline_id,
                    verify_run_id=verify_id,
                ),
                [
                    PatchFile(
                        path=change.path,
                        change_type=change.change_type,
                        additions=by_path[change.path].additions if change.path in by_path else 0,
                        deletions=by_path[change.path].deletions if change.path in by_path else 0,
                        language=detect_language(
                            change.path, (change.new or change.old or "")[:200]
                        ),
                        old_content=change.old,
                        new_content=change.new,
                    )
                    for change in sorted(result.changes, key=lambda c: c.path)
                ],
            )
            current.status = TaskStatus.AWAITING_REVIEW
            current.skill = result.skill
            current.patch_count = revision
            current.error = current.error_code = None
            current.finished_at = datetime.now(UTC)
            usage = dict(current.usage or {})
            for key, value in result.usage.as_dict().items():
                usage[key] = int(usage.get(key, 0)) + value
            current.usage = usage
            await tasks.append_trace(
                task.id, _event(f"Proposed revision {revision} for review.", "success")
            )
            await session.commit()

    async def reap_stale(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=self.c.settings.stale_job_minutes)
        resend: list[Job] = []
        async with self.c.db.session() as session:
            tasks = TaskRepository(session)
            for task in await tasks.unfinished_before(cutoff):
                if task.status == TaskStatus.APPLYING:
                    resend_patch = await PatchRepository(session).latest(task.id)
                    if resend_patch is not None:
                        resend.append(Job(JobType.APPLY_PATCH, task.workspace_id, resend_patch.id))
                    task.updated_at = datetime.now(UTC)
                elif task.attempts >= MAX_ATTEMPTS:
                    task.status = TaskStatus.FAILED
                    task.error_code = "stalled"
                    task.error = "The agent run did not finish after several attempts."
                else:
                    task.status = TaskStatus.QUEUED
                    task.updated_at = datetime.now(UTC)
                    resend.append(Job(JobType.RUN_TASK, task.workspace_id, task.id))
            await session.commit()
        for job in resend:
            await self.c.queue.enqueue(job)
        return len(resend)


def _event(message: str, kind: str) -> dict[str, Any]:
    return {"at": datetime.now(UTC).isoformat(), "message": message, "kind": kind}


def _describe_run(label: str, outcome: str, summary: Any) -> str:
    if summary is None or not getattr(summary, "total", 0):
        return f"{label} tests: {outcome}."
    parts = [f"{summary.passed} passed"]
    if summary.failed:
        parts.append(f"{summary.failed} failed")
    if summary.errors:
        parts.append(f"{summary.errors} errors")
    return f"{label} tests: {', '.join(parts)} of {summary.total}."
