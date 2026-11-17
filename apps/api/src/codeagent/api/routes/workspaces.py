"""Workspaces, members, API keys and the audit trail."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from codeagent.api.deps import AccessDep, ContainerDep, SessionDep, UserDep
from codeagent.api.routes.auth import workspace_summaries
from codeagent.core.errors import ForbiddenError
from codeagent.models import Workspace
from codeagent.models.enums import Role
from codeagent.repositories.audit import AuditRepository
from codeagent.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from codeagent.schemas.audit import AuditEventOut
from codeagent.schemas.auth import WorkspaceSummaryOut
from codeagent.schemas.common import Ok
from codeagent.schemas.overview import OverviewOut
from codeagent.schemas.workspaces import (
    MemberAdd,
    MemberAdded,
    MemberOut,
    MemberUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceSettings,
    WorkspaceUpdate,
)
from codeagent.services.api_keys import ApiKeyService
from codeagent.services.overview import OverviewService
from codeagent.services.principal import Principal
from codeagent.services.workspaces import WorkspaceService

router = APIRouter(tags=["workspaces"])


def _out(workspace: Workspace, role: str) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        slug=workspace.slug,
        name=workspace.name,
        description=workspace.description,
        settings=WorkspaceSettings.model_validate(workspace.settings or {}),
        role=role,
        created_at=workspace.created_at,
    )


@router.get("/workspaces", summary="Workspaces you belong to")
async def list_workspaces(
    user: UserDep, container: ContainerDep, session: SessionDep
) -> list[WorkspaceSummaryOut]:
    return await workspace_summaries(user, container, session)


@router.post("/workspaces", summary="Create a workspace", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate, user: UserDep, container: ContainerDep, session: SessionDep
) -> WorkspaceOut:
    workspace = await WorkspaceService(container, session).create(
        Principal(user=user), body.name, body.description
    )
    return _out(workspace, Role.OWNER.value)


@router.get("/workspaces/{workspace}", summary="A workspace and your role in it")
async def get_workspace(access: AccessDep) -> WorkspaceOut:
    return _out(access.workspace, access.role.value)


@router.patch("/workspaces/{workspace}", summary="Rename a workspace or change its settings")
async def update_workspace(
    body: WorkspaceUpdate, access: AccessDep, container: ContainerDep, session: SessionDep
) -> WorkspaceOut:
    access.require(Role.OWNER)
    workspace = await WorkspaceService(container, session).update(
        access.workspace,
        access.principal,
        name=body.name,
        description=body.description,
        settings=body.settings,
    )
    return _out(workspace, access.role.value)


@router.delete(
    "/workspaces/{workspace}",
    summary="Delete a workspace and everything in it",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workspace(access: AccessDep, container: ContainerDep, session: SessionDep) -> None:
    access.require(Role.OWNER)
    if access.principal.user is None:
        raise ForbiddenError("Only a person can delete a workspace.")
    await WorkspaceService(container, session).delete(access.workspace)


@router.get("/workspaces/{workspace}/overview", summary="Totals, daily series and recent work")
async def overview(
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> OverviewOut:
    return await OverviewService(container, session).get(access.workspace, days)


@router.get("/workspaces/{workspace}/members", summary="Members and their roles")
async def list_members(
    access: AccessDep, container: ContainerDep, session: SessionDep
) -> list[MemberOut]:
    rows = await WorkspaceService(container, session).members(access.workspace.id)
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post(
    "/workspaces/{workspace}/members",
    summary="Add a person (an account is created with a temporary password if needed)",
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    body: MemberAdd, access: AccessDep, container: ContainerDep, session: SessionDep
) -> MemberAdded:
    access.require(Role.OWNER)
    membership, user, password = await WorkspaceService(container, session).add_member(
        access.workspace, access.principal, body.email, body.name, Role(body.role)
    )
    return MemberAdded(
        member=MemberOut(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=membership.role,
            joined_at=membership.created_at,
        ),
        temporary_password=password,
    )


@router.patch("/workspaces/{workspace}/members/{user_id}", summary="Change a member's role")
async def change_member(
    user_id: uuid.UUID,
    body: MemberUpdate,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> Ok:
    access.require(Role.OWNER)
    await WorkspaceService(container, session).change_role(
        access.workspace, access.principal, user_id, Role(body.role)
    )
    return Ok()


@router.delete(
    "/workspaces/{workspace}/members/{user_id}",
    summary="Remove a member",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    user_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> None:
    access.require(Role.OWNER)
    await WorkspaceService(container, session).remove_member(
        access.workspace, access.principal, user_id
    )


@router.get("/workspaces/{workspace}/audit", summary="The audit trail, newest first")
async def audit_trail(
    access: AccessDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEventOut]:
    access.require(Role.OWNER)
    rows = await AuditRepository(session).recent(access.workspace.id, limit=limit, offset=offset)
    return [
        AuditEventOut(
            id=event.id,
            action=event.action,
            target_type=event.target_type,
            target_id=event.target_id,
            details=event.details,
            actor_name=name or ("API key" if event.actor_api_key_id else None),
            created_at=event.created_at,
        )
        for event, name in rows
    ]


@router.get("/workspaces/{workspace}/api-keys", summary="API keys of the workspace")
async def list_keys(
    access: AccessDep, container: ContainerDep, session: SessionDep
) -> list[ApiKeyOut]:
    access.require(Role.OWNER)
    keys = await ApiKeyService(container, session).for_workspace(access.workspace.id)
    return [ApiKeyOut.model_validate(key) for key in keys]


@router.post(
    "/workspaces/{workspace}/api-keys",
    summary="Create an API key (the secret is shown once)",
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    body: ApiKeyCreate, access: AccessDep, container: ContainerDep, session: SessionDep
) -> ApiKeyCreated:
    access.require(Role.OWNER)
    if access.principal.user is None:
        raise ForbiddenError("API keys cannot create API keys.")
    key, plaintext = await ApiKeyService(container, session).create(
        access.workspace, access.principal, body.name, body.role, body.expires_in_days
    )
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=plaintext)


@router.delete(
    "/workspaces/{workspace}/api-keys/{key_id}",
    summary="Revoke an API key",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_key(
    key_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> None:
    access.require(Role.OWNER)
    await ApiKeyService(container, session).revoke(access.workspace, access.principal, key_id)
