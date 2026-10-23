"""Code repositories and their snapshots."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update

from codeagent.models import Repository, Snapshot
from codeagent.models.enums import IndexStatus
from codeagent.repositories.base import Store


@dataclass(frozen=True, slots=True)
class SearchScope:
    """A repository whose current snapshot a search or an answer reads."""

    repository_id: uuid.UUID
    slug: str
    name: str
    snapshot_id: uuid.UUID


class ReposRepository(Store):
    async def get(self, workspace_id: uuid.UUID, repository_id: uuid.UUID) -> Repository | None:
        result = await self.session.execute(
            select(Repository).where(
                Repository.id == repository_id, Repository.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def by_slug(self, workspace_id: uuid.UUID, slug: str) -> Repository | None:
        result = await self.session.execute(
            select(Repository).where(
                Repository.workspace_id == workspace_id, Repository.slug == slug
            )
        )
        return result.scalar_one_or_none()

    async def by_ref(self, workspace_id: uuid.UUID, ref: str) -> Repository | None:
        try:
            return await self.get(workspace_id, uuid.UUID(ref))
        except ValueError:
            return await self.by_slug(workspace_id, ref.lower())

    async def slug_taken(self, workspace_id: uuid.UUID, slug: str) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count()).where(
                    Repository.workspace_id == workspace_id, Repository.slug == slug
                )
            )
        )

    async def add(self, repository: Repository) -> Repository:
        self.session.add(repository)
        await self.session.flush()
        return repository

    async def page(
        self,
        workspace_id: uuid.UUID,
        *,
        query: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Repository], int]:
        conditions: list[Any] = [Repository.workspace_id == workspace_id]
        if status:
            conditions.append(Repository.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(or_(Repository.name.ilike(pattern), Repository.slug.ilike(pattern)))
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            select(Repository)
            .where(*conditions)
            .order_by(Repository.name, Repository.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total

    async def scopes(
        self, workspace_id: uuid.UUID, repository_ids: Sequence[uuid.UUID] | None = None
    ) -> list[SearchScope]:
        """Repositories with a ready index, and the snapshot each one serves."""
        conditions: list[Any] = [
            Repository.workspace_id == workspace_id,
            Repository.current_snapshot_id.is_not(None),
        ]
        if repository_ids:
            conditions.append(Repository.id.in_(list(repository_ids)))
        result = await self.session.execute(
            select(
                Repository.id, Repository.slug, Repository.name, Repository.current_snapshot_id
            ).where(*conditions)
        )
        return [
            SearchScope(row.id, row.slug, row.name, row.current_snapshot_id)
            for row in result.all()
            if row.current_snapshot_id is not None
        ]

    async def mark(self, repository_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(
            update(Repository).where(Repository.id == repository_id).values(**values)
        )

    async def counts_by_status(self, workspace_id: uuid.UUID) -> dict[str, int]:
        rows = await self.session.execute(
            select(Repository.status, func.count())
            .where(Repository.workspace_id == workspace_id)
            .group_by(Repository.status)
        )
        return {status: int(count) for status, count in rows.all()}

    async def totals(self, workspace_id: uuid.UUID) -> tuple[int, int, int]:
        """(files, symbols, lines) across the current snapshots of the workspace."""
        row = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(Repository.file_count), 0),
                    func.coalesce(func.sum(Repository.symbol_count), 0),
                    func.coalesce(func.sum(Repository.line_count), 0),
                ).where(Repository.workspace_id == workspace_id)
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2])


class SnapshotRepository(Store):
    async def get(self, workspace_id: uuid.UUID, snapshot_id: uuid.UUID) -> Snapshot | None:
        result = await self.session.execute(
            select(Snapshot).where(
                Snapshot.id == snapshot_id, Snapshot.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(
        self, workspace_id: uuid.UUID, snapshot_id: uuid.UUID
    ) -> Snapshot | None:
        result = await self.session.execute(
            select(Snapshot)
            .where(Snapshot.id == snapshot_id, Snapshot.workspace_id == workspace_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add(self, snapshot: Snapshot) -> Snapshot:
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def for_repository(
        self, workspace_id: uuid.UUID, repository_id: uuid.UUID, *, limit: int
    ) -> list[Snapshot]:
        result = await self.session.execute(
            select(Snapshot)
            .where(Snapshot.workspace_id == workspace_id, Snapshot.repository_id == repository_id)
            .order_by(Snapshot.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def busy(self, repository_id: uuid.UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count()).where(
                    Snapshot.repository_id == repository_id,
                    Snapshot.status.in_([IndexStatus.QUEUED, IndexStatus.INDEXING]),
                )
            )
        )

    async def prune(self, repository_id: uuid.UUID, keep: int, current: uuid.UUID) -> int:
        """Delete ready or failed snapshots beyond the newest `keep` (never the current one)."""
        kept = (
            select(Snapshot.id)
            .where(Snapshot.repository_id == repository_id)
            .order_by(Snapshot.created_at.desc())
            .limit(keep)
        )
        result = await self.session.execute(
            delete(Snapshot).where(
                Snapshot.repository_id == repository_id,
                Snapshot.id.not_in(kept),
                Snapshot.id != current,
                Snapshot.status.in_([IndexStatus.READY, IndexStatus.FAILED]),
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def unfinished_before(self, cutoff: datetime, limit: int = 100) -> list[Snapshot]:
        result = await self.session.execute(
            select(Snapshot)
            .where(
                Snapshot.status.in_([IndexStatus.QUEUED, IndexStatus.INDEXING]),
                Snapshot.updated_at < cutoff,
            )
            .order_by(Snapshot.updated_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def mark(self, snapshot_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(
            update(Snapshot).where(Snapshot.id == snapshot_id).values(**values)
        )
