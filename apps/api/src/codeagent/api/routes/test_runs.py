"""Sandboxed test runs: start one, follow it, read its results and log."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from codeagent.api.deps import AccessDep, ContainerDep, RunLimit, SessionDep
from codeagent.api.presenters import test_run_out
from codeagent.models.enums import Role
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.tasks import TaskRepository
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.schemas.test_runs import TestCaseOut, TestRunDetail, TestRunOut, TestRunPage
from codeagent.services.repositories import RepositoryService
from codeagent.services.test_runs import TestRunService

router = APIRouter(tags=["test runs"])


@router.get("/workspaces/{workspace}/test-runs", summary="Test runs, newest first")
async def list_runs(
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    repository: Annotated[str | None, Query(max_length=64)] = None,
    task: Annotated[int | None, Query(ge=1, description="Task number.")] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    trigger: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TestRunPage:
    repository_id = (
        (await RepositoryService(container, session).get(access.workspace.id, repository)).id
        if repository
        else None
    )
    task_id = None
    if task is not None:
        found = await TaskRepository(session).by_number(access.workspace.id, task)
        task_id = found.id if found else None
        if found is None:
            return TestRunPage(items=[], total=0, limit=limit, offset=offset)
    rows, total = await TestRunRepository(session).page(
        access.workspace.id,
        repository_id=repository_id,
        task_id=task_id,
        status=status_filter,
        trigger=trigger,
        limit=limit,
        offset=offset,
    )
    return TestRunPage(
        items=[test_run_out(run, slug, number) for run, slug, number in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workspaces/{workspace}/repositories/{repo}/test-runs",
    summary="Run the repository's tests in the sandbox",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RunLimit],
)
async def start_run(
    repo: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> TestRunOut:
    access.require(Role.DEVELOPER)
    repository = await RepositoryService(container, session).get(access.workspace.id, repo)
    run = await TestRunService(container, session).start(
        access.workspace, access.principal, repository
    )
    return test_run_out(run, repository.slug, None)


@router.get("/workspaces/{workspace}/test-runs/{ref}", summary="A run with per-test results")
async def get_run(
    ref: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> TestRunDetail:
    service = TestRunService(container, session)
    run = await service.get(access.workspace.id, ref)
    repository = await ReposRepository(session).get(access.workspace.id, run.repository_id)
    task_number = None
    if run.task_id:
        task = await TaskRepository(session).get(access.workspace.id, run.task_id)
        task_number = task.number if task else None
    base = test_run_out(run, repository.slug if repository else "", task_number)
    return TestRunDetail(
        **base.model_dump(),
        limits=run.limits or {},
        results=[TestCaseOut.model_validate(case) for case in run.results or []],
        log_tail=run.log_tail,
        log_truncated=run.log_truncated,
        has_full_log=run.log_key is not None,
    )


@router.get("/workspaces/{workspace}/test-runs/{ref}/log", summary="The full log, as text")
async def get_log(
    ref: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> Response:
    service = TestRunService(container, session)
    run = await service.get(access.workspace.id, ref)
    return Response(await service.full_log(run), media_type="text/plain; charset=utf-8")
