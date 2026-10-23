from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import aliased

from codeagent.models import Membership, Repository, User, Workspace
from codeagent.models.enums import Role
from codeagent.repositories.base import Store


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    workspace: Workspace
    role: str
    repository_count: int
    member_count: int


class WorkspaceRepository(Store):
    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        return await self.session.get(Workspace, workspace_id)

    async def by_slug(self, slug: str) -> Workspace | None:
        result = await self.session.execute(select(Workspace).where(Workspace.slug == slug))
        return result.scalar_one_or_none()

    async def slug_taken(self, slug: str) -> bool:
        return bool(await self.session.scalar(select(func.count()).where(Workspace.slug == slug)))

    async def add(self, workspace: Workspace) -> Workspace:
        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def membership(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
        return await self.session.get(Membership, (workspace_id, user_id))

    async def for_user(self, user_id: uuid.UUID) -> list[WorkspaceSummary]:
        repositories = (
            select(func.count())
            .where(Repository.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        # The outer query joins memberships too; counting through an alias keeps the
        # subquery from correlating to the caller's own membership row.
        everyone = aliased(Membership)
        members = (
            select(func.count())
            .select_from(everyone)
            .where(everyone.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Workspace, Membership.role, repositories, members)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user_id)
            .order_by(Workspace.name)
        )
        return [WorkspaceSummary(w, role, repos, people) for w, role, repos, people in result.all()]

    async def members(self, workspace_id: uuid.UUID) -> list[tuple[Membership, User]]:
        result = await self.session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == workspace_id)
            .order_by(Membership.created_at)
        )
        return [(m, u) for m, u in result.all()]

    async def owner_count(self, workspace_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(
                    Membership.workspace_id == workspace_id, Membership.role == Role.OWNER
                )
            )
            or 0
        )

    async def add_member(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, role: Role
    ) -> Membership:
        membership = Membership(workspace_id=workspace_id, user_id=user_id, role=role.value)
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def next_task_number(self, workspace_id: uuid.UUID) -> int:
        """Allocate the next task number; the row lock serialises concurrent requests."""
        return int(
            await self.session.scalar(
                update(Workspace)
                .where(Workspace.id == workspace_id)
                .values(task_counter=Workspace.task_counter + 1)
                .returning(Workspace.task_counter)
            )
            or 0
        )

    async def next_run_number(self, workspace_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                update(Workspace)
                .where(Workspace.id == workspace_id)
                .values(run_counter=Workspace.run_counter + 1)
                .returning(Workspace.run_counter)
            )
            or 0
        )
