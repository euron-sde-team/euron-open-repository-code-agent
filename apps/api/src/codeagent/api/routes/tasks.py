"""Tasks for the agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from codeagent.api.deps import AccessDep, ContainerDep, SessionDep, TaskLimit
from codeagent.api.presenters import patch_summary, run_summary, task_out
from codeagent.models.enums import Role
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.tasks import PatchRepository, TaskRepository
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.repositories.users import UserRepository
from codeagent.schemas.tasks import (
    TaskCreate,
    TaskDetail,
    TaskOut,
    TaskPage,
    TaskRetry,
    TraceEvent,
)
from codeagent.services.repositories import RepositoryService
from codeagent.services.tasks import TaskService, can_decide

router = APIRouter(tags=["tasks"])


@router.get("/workspaces/{workspace}/tasks", summary="Tasks, newest first")
async def list_tasks(
    access: AccessDep,
    session: SessionDep,
    container: ContainerDep,
    status_filter: Annotated[
        str | None, Query(alias="status", max_length=20, description="A status, or `open`.")
    ] = None,
    repository: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskPage:
    repository_id = (
        (await RepositoryService(container, session).get(access.workspace.id, repository)).id
        if repository
        else None
    )
    rows, total = await TaskRepository(session).page(
        access.workspace.id,
        status=status_filter,
        repository_id=repository_id,
        query=q,
        limit=limit,
        offset=offset,
    )
    return TaskPage(
        items=[task_out(task, slug, name) for task, slug, name in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workspaces/{workspace}/tasks",
    summary="Describe a change for the agent to propose",
    status_code=status.HTTP_201_CREATED,
    dependencies=[TaskLimit],
)
async def create_task(
    body: TaskCreate, access: AccessDep, container: ContainerDep, session: SessionDep
) -> TaskOut:
    access.require(Role.DEVELOPER)
    repository = await RepositoryService(container, session).get(
        access.workspace.id, body.repository
    )
    task = await TaskService(container, session).create(
        access.workspace, access.principal, repository, body.title, body.description
    )
    return task_out(
        task, repository.slug, access.principal.user.name if access.principal.user else None
    )


async def _detail(
    access: AccessDep, container: ContainerDep, session: SessionDep, ref: str
) -> TaskDetail:
    task = await TaskService(container, session).get(access.workspace.id, ref)
    repository = await ReposRepository(session).get(access.workspace.id, task.repository_id)
    requester = await UserRepository(session).get(task.created_by) if task.created_by else None
    patches = await PatchRepository(session).for_task(task.id)
    runs, _ = await TestRunRepository(session).page(
        access.workspace.id,
        repository_id=None,
        task_id=task.id,
        status=None,
        trigger=None,
        limit=20,
        offset=0,
    )
    current = next((p for p in patches if p.status == "proposed"), None)
    base = task_out(
        task, repository.slug if repository else "", requester.name if requester else None
    )
    return TaskDetail(
        **base.model_dump(),
        description=task.description,
        base_commit=task.base_commit,
        error_code=task.error_code,
        trace=[TraceEvent.model_validate(event) for event in task.trace or []],
        usage=task.usage or {},
        started_at=task.started_at,
        finished_at=task.finished_at,
        patches=[patch_summary(p) for p in patches],
        runs=[run_summary(run) for run, _, _ in runs],
        can_approve=can_decide(task, current, access.principal, access.role, access.workspace),
    )


@router.get("/workspaces/{workspace}/tasks/{ref}", summary="A task with its trace and patches")
async def get_task(
    ref: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> TaskDetail:
    return await _detail(access, container, session, ref)


@router.post(
    "/workspaces/{workspace}/tasks/{ref}/retry",
    summary="Run the task again (optionally with a new description)",
    dependencies=[TaskLimit],
)
async def retry_task(
    ref: str,
    body: TaskRetry,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> TaskDetail:
    access.require(Role.DEVELOPER)
    service = TaskService(container, session)
    task = await service.get(access.workspace.id, ref)
    await service.retry(access.workspace, access.principal, task, body.description)
    return await _detail(access, container, session, ref)


@router.post("/workspaces/{workspace}/tasks/{ref}/cancel", summary="Cancel a queued task")
async def cancel_task(
    ref: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> TaskDetail:
    access.require(Role.DEVELOPER)
    service = TaskService(container, session)
    task = await service.get(access.workspace.id, ref)
    await service.cancel(access.workspace, access.principal, task)
    return await _detail(access, container, session, ref)
