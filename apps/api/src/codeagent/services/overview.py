"""The workspace dashboard: totals, a daily series and the most recent work."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.core.logging import get_logger
from codeagent.models import Workspace
from codeagent.models.enums import IndexStatus, PatchStatus, TaskStatus
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.tasks import PatchRepository, TaskRepository
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.repositories.usage import UsageRepository
from codeagent.schemas.overview import (
    ActivityItem,
    DayPoint,
    OverviewOut,
    OverviewTotals,
    TaskStatusCount,
)
from codeagent.services.container import Container

log = get_logger("codeagent.overview")
CACHE_TTL_S = 30
RECENT = 10


class OverviewService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session

    @staticmethod
    def _key(workspace_id: uuid.UUID, days: int) -> str:
        return f"overview:{workspace_id}:{days}"

    async def get(self, workspace: Workspace, days: int) -> OverviewOut:
        key = self._key(workspace.id, days)
        try:
            cached = await self.c.redis.get(key)
        except Exception:
            cached = None
        if cached:
            return OverviewOut.model_validate(orjson.loads(cached))
        overview = await self._build(workspace, days)
        try:
            await self.c.redis.set(key, overview.model_dump_json().encode(), ex=CACHE_TTL_S)
        except Exception:
            log.warning("overview_cache_write_failed")
        return overview

    async def _build(self, workspace: Workspace, days: int) -> OverviewOut:
        now = datetime.now(UTC)
        since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        repos, tasks = ReposRepository(self.session), TaskRepository(self.session)
        patches, runs = PatchRepository(self.session), TestRunRepository(self.session)
        usage = UsageRepository(self.session)

        repo_status = await repos.counts_by_status(workspace.id)
        files, symbols, lines = await repos.totals(workspace.id)
        task_status = await tasks.counts_by_status(workspace.id, since)
        patch_status = await patches.counts_by_status(workspace.id)
        run_count, run_passed, median_ms = await runs.totals(workspace.id, since)
        questions, searches, tokens, _ = await usage.totals(workspace.id, since)

        decided = sum(
            patch_status.get(s, 0)
            for s in (PatchStatus.APPROVED, PatchStatus.APPLYING, PatchStatus.APPLIED)
        )
        rejected = patch_status.get(PatchStatus.REJECTED, 0)
        totals = OverviewTotals(
            repositories=sum(repo_status.values()),
            repositories_ready=repo_status.get(IndexStatus.READY, 0),
            files=files,
            symbols=symbols,
            lines=lines,
            open_reviews=patch_status.get(PatchStatus.PROPOSED, 0),
            tasks=sum(task_status.values()),
            tasks_applied=task_status.get(TaskStatus.APPLIED, 0),
            tasks_failed=task_status.get(TaskStatus.FAILED, 0),
            approval_rate=round(decided / (decided + rejected), 3) if decided + rejected else 0.0,
            test_runs=run_count,
            test_pass_rate=round(run_passed / run_count, 3) if run_count else 0.0,
            median_run_ms=median_ms,
            questions=questions,
            searches=searches,
            model_tokens=tokens,
            median_review_hours=await patches.review_hours(workspace.id, since),
        )

        by_day: dict[str, DayPoint] = {}
        for offset in range(days):
            day = (since + timedelta(days=offset)).date().isoformat()
            by_day[day] = DayPoint(day=day, runs_passed=0, runs_failed=0, questions=0, searches=0)
        for point in await runs.daily(workspace.id, since):
            if point.day in by_day:
                by_day[point.day].runs_passed = point.passed
                by_day[point.day].runs_failed = point.failed
        for use in await usage.daily(workspace.id, since):
            if use.day in by_day:
                by_day[use.day].questions = use.questions
                by_day[use.day].searches = use.searches

        return OverviewOut(
            days=days,
            totals=totals,
            daily=[by_day[d] for d in sorted(by_day, key=date.fromisoformat)],
            tasks_by_status=[
                TaskStatusCount(status=s, count=c)
                for s, c in sorted(task_status.items(), key=lambda kv: -kv[1])
            ],
            recent=await self._recent(workspace),
            workspace_id=workspace.id,
        )

    async def _recent(self, workspace: Workspace) -> list[ActivityItem]:
        base = f"/w/{workspace.slug}"
        items: list[ActivityItem] = []
        for task, repo_slug, actor in await TaskRepository(self.session).recent(
            workspace.id, RECENT
        ):
            items.append(
                ActivityItem(
                    kind="task",
                    title=f"#{task.number} {task.title}",
                    detail=repo_slug,
                    status=task.status,
                    href=f"{base}/tasks/{task.number}",
                    at=task.updated_at,
                    actor=actor,
                )
            )
        run_rows, _ = await TestRunRepository(self.session).page(
            workspace.id,
            repository_id=None,
            task_id=None,
            status=None,
            trigger=None,
            limit=RECENT,
            offset=0,
        )
        for run, repo_slug, _task_number in run_rows:
            items.append(
                ActivityItem(
                    kind="test_run",
                    title=f"Test run #{run.number}",
                    detail=f"{repo_slug}: {run.passed} passed, {run.failed + run.errors} failed",
                    status=run.status,
                    href=f"{base}/runs/{run.number}",
                    at=run.updated_at,
                    actor=None,
                )
            )
        items.sort(key=lambda item: item.at, reverse=True)
        return items[:RECENT]
