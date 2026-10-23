from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Date, cast, func, select, update

from codeagent.models import Repository, Task, TestRun
from codeagent.models.enums import RunStatus
from codeagent.repositories.base import Store


@dataclass(frozen=True, slots=True)
class DailyRuns:
    day: str
    passed: int
    failed: int


class TestRunRepository(Store):
    __test__ = False

    async def get(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> TestRun | None:
        result = await self.session.execute(
            select(TestRun).where(TestRun.id == run_id, TestRun.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def by_number(self, workspace_id: uuid.UUID, number: int) -> TestRun | None:
        result = await self.session.execute(
            select(TestRun).where(TestRun.workspace_id == workspace_id, TestRun.number == number)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> TestRun | None:
        result = await self.session.execute(
            select(TestRun)
            .where(TestRun.id == run_id, TestRun.workspace_id == workspace_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add(self, run: TestRun) -> TestRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def page(
        self,
        workspace_id: uuid.UUID,
        *,
        repository_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        status: str | None,
        trigger: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[TestRun, str, int | None]], int]:
        conditions: list[Any] = [TestRun.workspace_id == workspace_id]
        if repository_id:
            conditions.append(TestRun.repository_id == repository_id)
        if task_id:
            conditions.append(TestRun.task_id == task_id)
        if status:
            conditions.append(TestRun.status == status)
        if trigger:
            conditions.append(TestRun.trigger == trigger)
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            select(TestRun, Repository.slug, Task.number)
            .join(Repository, Repository.id == TestRun.repository_id)
            .outerjoin(Task, Task.id == TestRun.task_id)
            .where(*conditions)
            .order_by(TestRun.number.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(run, slug, number) for run, slug, number in result.all()], total

    async def for_patch(self, patch_id: uuid.UUID) -> list[TestRun]:
        result = await self.session.execute(
            select(TestRun).where(TestRun.patch_id == patch_id).order_by(TestRun.number.desc())
        )
        return list(result.scalars())

    async def mark(self, run_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(update(TestRun).where(TestRun.id == run_id).values(**values))

    async def unfinished_before(self, cutoff: datetime, limit: int = 100) -> list[TestRun]:
        result = await self.session.execute(
            select(TestRun)
            .where(
                TestRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                TestRun.updated_at < cutoff,
                TestRun.trigger.in_(["manual", "patch"]),
            )
            .order_by(TestRun.updated_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def daily(self, workspace_id: uuid.UUID, since: datetime) -> list[DailyRuns]:
        day = cast(func.date_trunc("day", TestRun.created_at), Date)
        rows = await self.session.execute(
            select(
                day.label("day"),
                func.count().filter(TestRun.status == RunStatus.PASSED),
                func.count().filter(
                    TestRun.status.in_([RunStatus.FAILED, RunStatus.ERROR, RunStatus.TIMED_OUT])
                ),
            )
            .where(TestRun.workspace_id == workspace_id, TestRun.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        return [DailyRuns(d.isoformat(), int(p), int(f)) for d, p, f in rows.all()]

    async def totals(self, workspace_id: uuid.UUID, since: datetime) -> tuple[int, int, int]:
        """(finished runs, passed runs, median duration in ms) since `since`."""
        row = (
            await self.session.execute(
                select(
                    func.count().filter(
                        TestRun.status.in_(
                            [
                                RunStatus.PASSED,
                                RunStatus.FAILED,
                                RunStatus.ERROR,
                                RunStatus.TIMED_OUT,
                            ]
                        )
                    ),
                    func.count().filter(TestRun.status == RunStatus.PASSED),
                    func.coalesce(func.percentile_cont(0.5).within_group(TestRun.duration_ms), 0),
                ).where(TestRun.workspace_id == workspace_id, TestRun.created_at >= since)
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2])
