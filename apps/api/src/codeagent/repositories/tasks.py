"""Tasks, patch revisions, their files and review comments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import orjson
from sqlalchemy import func, select, text, update

from codeagent.models import Patch, PatchFile, Repository, ReviewComment, Task, User
from codeagent.models.enums import PatchStatus, TaskStatus
from codeagent.repositories.base import Store

_APPEND_TRACE = text(
    "UPDATE tasks SET trace = trace || CAST(:event AS jsonb), updated_at = now() WHERE id = :id"
)


class TaskRepository(Store):
    async def get(self, workspace_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, workspace_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        result = await self.session.execute(
            select(Task)
            .where(Task.id == task_id, Task.workspace_id == workspace_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def by_number(self, workspace_id: uuid.UUID, number: int) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.workspace_id == workspace_id, Task.number == number)
        )
        return result.scalar_one_or_none()

    async def add(self, task: Task) -> Task:
        self.session.add(task)
        await self.session.flush()
        return task

    async def page(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None,
        repository_id: uuid.UUID | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Task, str, str | None]], int]:
        conditions: list[Any] = [Task.workspace_id == workspace_id]
        if status == "open":
            conditions.append(
                Task.status.in_(
                    [
                        TaskStatus.QUEUED,
                        TaskStatus.RUNNING,
                        TaskStatus.AWAITING_REVIEW,
                        TaskStatus.APPROVED,
                        TaskStatus.APPLYING,
                    ]
                )
            )
        elif status:
            conditions.append(Task.status == status)
        if repository_id:
            conditions.append(Task.repository_id == repository_id)
        if query:
            conditions.append(Task.title.ilike(f"%{query.strip()}%"))
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            select(Task, Repository.slug, User.name)
            .join(Repository, Repository.id == Task.repository_id)
            .outerjoin(User, User.id == Task.created_by)
            .where(*conditions)
            .order_by(Task.number.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(task, slug, name) for task, slug, name in result.all()], total

    async def append_trace(self, task_id: uuid.UUID, event: dict[str, Any]) -> None:
        """Atomic append, so progress notes never overwrite each other."""
        await self.session.execute(
            _APPEND_TRACE, {"event": orjson.dumps([event]).decode(), "id": task_id}
        )

    async def counts_by_status(
        self, workspace_id: uuid.UUID, since: datetime | None = None
    ) -> dict[str, int]:
        conditions: list[Any] = [Task.workspace_id == workspace_id]
        if since is not None:
            conditions.append(Task.created_at >= since)
        rows = await self.session.execute(
            select(Task.status, func.count()).where(*conditions).group_by(Task.status)
        )
        return {status: int(count) for status, count in rows.all()}

    async def unfinished_before(self, cutoff: datetime, limit: int = 100) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .where(
                Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.APPLYING]),
                Task.updated_at < cutoff,
            )
            .order_by(Task.updated_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def recent(
        self, workspace_id: uuid.UUID, limit: int
    ) -> list[tuple[Task, str, str | None]]:
        items, _ = await self.page(
            workspace_id, status=None, repository_id=None, query=None, limit=limit, offset=0
        )
        return items


class PatchRepository(Store):
    async def get(self, workspace_id: uuid.UUID, patch_id: uuid.UUID) -> Patch | None:
        result = await self.session.execute(
            select(Patch).where(Patch.id == patch_id, Patch.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, workspace_id: uuid.UUID, patch_id: uuid.UUID) -> Patch | None:
        result = await self.session.execute(
            select(Patch)
            .where(Patch.id == patch_id, Patch.workspace_id == workspace_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def for_task(self, task_id: uuid.UUID) -> list[Patch]:
        result = await self.session.execute(
            select(Patch).where(Patch.task_id == task_id).order_by(Patch.revision.desc())
        )
        return list(result.scalars())

    async def latest(self, task_id: uuid.UUID) -> Patch | None:
        result = await self.session.execute(
            select(Patch).where(Patch.task_id == task_id).order_by(Patch.revision.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def add(self, patch: Patch, files: list[PatchFile]) -> Patch:
        self.session.add(patch)
        await self.session.flush()
        for file in files:
            file.patch_id = patch.id
            self.session.add(file)
        await self.session.flush()
        return patch

    async def files(self, patch_id: uuid.UUID) -> list[PatchFile]:
        result = await self.session.execute(
            select(PatchFile).where(PatchFile.patch_id == patch_id).order_by(PatchFile.path)
        )
        return list(result.scalars())

    async def supersede_proposed(self, task_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Patch)
            .where(Patch.task_id == task_id, Patch.status == PatchStatus.PROPOSED)
            .values(status=PatchStatus.SUPERSEDED)
        )

    async def comments(self, patch_id: uuid.UUID) -> list[tuple[ReviewComment, str | None]]:
        result = await self.session.execute(
            select(ReviewComment, User.name)
            .outerjoin(User, User.id == ReviewComment.author_id)
            .where(ReviewComment.patch_id == patch_id)
            .order_by(ReviewComment.created_at, ReviewComment.id)
        )
        return [(comment, name) for comment, name in result.all()]

    async def comment(self, workspace_id: uuid.UUID, comment_id: uuid.UUID) -> ReviewComment | None:
        result = await self.session.execute(
            select(ReviewComment).where(
                ReviewComment.id == comment_id, ReviewComment.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def add_comment(self, comment: ReviewComment) -> ReviewComment:
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def counts_by_status(self, workspace_id: uuid.UUID) -> dict[str, int]:
        rows = await self.session.execute(
            select(Patch.status, func.count())
            .where(Patch.workspace_id == workspace_id)
            .group_by(Patch.status)
        )
        return {status: int(count) for status, count in rows.all()}

    async def review_hours(self, workspace_id: uuid.UUID, since: datetime) -> float | None:
        """Median time from proposal to decision, in hours, for patches decided since `since`."""
        value = await self.session.scalar(
            select(
                func.percentile_cont(0.5).within_group(
                    func.extract("epoch", Patch.decided_at - Patch.created_at) / 3600.0
                )
            ).where(
                Patch.workspace_id == workspace_id,
                Patch.decided_at.is_not(None),
                Patch.decided_at >= since,
            )
        )
        return float(value) if value is not None else None
