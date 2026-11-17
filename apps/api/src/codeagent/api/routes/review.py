"""Review a proposed patch: read the diff, comment, approve or reject, apply, export."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from codeagent.api.deps import AccessDep, ContainerDep, RunLimit, SessionDep
from codeagent.api.presenters import patch_summary, run_summary, test_run_out
from codeagent.core.errors import ForbiddenError, NotFoundError
from codeagent.models import Patch, ReviewComment
from codeagent.models.enums import Role
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.repositories.users import UserRepository
from codeagent.schemas.tasks import (
    ApplyRequest,
    CommentCreate,
    CommentOut,
    CommentUpdate,
    DecisionRequest,
    PatchFileOut,
    PatchOut,
    PlanStepOut,
    RunSummary,
)
from codeagent.schemas.test_runs import TestRunOut
from codeagent.services.review import ReviewService, diff_view
from codeagent.services.test_runs import TestRunService

router = APIRouter(tags=["review"])


def _comment(comment: ReviewComment, author: str | None) -> CommentOut:
    return CommentOut(
        id=comment.id,
        author=author,
        author_id=comment.author_id,
        body=comment.body,
        path=comment.path,
        line=comment.line,
        side=comment.side,
        resolved=comment.resolved,
        created_at=comment.created_at,
    )


async def _patch_out(
    access: AccessDep, container: ContainerDep, session: SessionDep, patch: Patch
) -> PatchOut:
    service = ReviewService(container, session)
    task = await service.task_of(patch)
    runs = TestRunRepository(session)
    decided_by = await UserRepository(session).get(patch.decided_by) if patch.decided_by else None

    async def run_of(run_id: uuid.UUID | None) -> RunSummary | None:
        run = await runs.get(access.workspace.id, run_id) if run_id else None
        return run_summary(run) if run else None

    return PatchOut(
        **patch_summary(patch).model_dump(),
        task_id=task.id,
        task_number=task.number,
        rationale=patch.rationale,
        plan=[PlanStepOut.model_validate(step) for step in patch.plan or []],
        base_commit=patch.base_commit,
        decision_note=patch.decision_note,
        decided_by=decided_by.name if decided_by else None,
        applied_at=patch.applied_at,
        apply_error=patch.apply_error,
        diff_files=[
            PatchFileOut.model_validate(dataclasses.asdict(view))
            for view in diff_view(patch, await service.files(patch))
        ],
        comments=[_comment(c, name) for c, name in await service.comments(patch)],
        baseline_run=await run_of(patch.baseline_run_id),
        verify_run=await run_of(patch.verify_run_id),
    )


@router.get("/workspaces/{workspace}/patches/{patch_id}", summary="A patch revision with its diff")
async def get_patch(
    patch_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> PatchOut:
    patch = await ReviewService(container, session).get(access.workspace.id, patch_id)
    return await _patch_out(access, container, session, patch)


@router.get(
    "/workspaces/{workspace}/patches/{patch_id}/export",
    summary="Download the patch as a plain diff or a git-am mbox patch",
)
async def export_patch(
    patch_id: uuid.UUID,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    format: Annotated[Literal["diff", "patch"], Query()] = "patch",
) -> Response:
    service = ReviewService(container, session)
    patch = await service.get(access.workspace.id, patch_id)
    filename, media_type, content = await service.export(patch, format)
    return Response(
        content,
        media_type=media_type,
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/workspaces/{workspace}/patches/{patch_id}/comments",
    summary="Comment on the patch or on a line of it",
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    patch_id: uuid.UUID,
    body: CommentCreate,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> CommentOut:
    access.require(Role.DEVELOPER)
    service = ReviewService(container, session)
    patch = await service.get(access.workspace.id, patch_id)
    comment = await service.add_comment(
        access.workspace,
        access.principal,
        patch,
        body=body.body,
        path=body.path,
        line=body.line,
        side=body.side,
    )
    return _comment(comment, access.principal.user.name if access.principal.user else None)


@router.patch("/workspaces/{workspace}/comments/{comment_id}", summary="Edit or resolve a comment")
async def update_comment(
    comment_id: uuid.UUID,
    body: CommentUpdate,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> CommentOut:
    access.require(Role.DEVELOPER)
    comment = await ReviewService(container, session).update_comment(
        access.workspace,
        access.principal,
        access.role,
        comment_id,
        body=body.body,
        resolved=body.resolved,
    )
    author = await UserRepository(session).get(comment.author_id) if comment.author_id else None
    return _comment(comment, author.name if author else None)


@router.delete(
    "/workspaces/{workspace}/comments/{comment_id}",
    summary="Delete a comment",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_comment(
    comment_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> None:
    access.require(Role.DEVELOPER)
    await ReviewService(container, session).delete_comment(
        access.workspace, access.principal, access.role, comment_id
    )


def _need_person(access: AccessDep) -> None:
    if access.principal.user is None:
        raise ForbiddenError("Reviews are decided by people, not API keys.")


@router.post("/workspaces/{workspace}/patches/{patch_id}/approve", summary="Approve a proposal")
async def approve(
    patch_id: uuid.UUID,
    body: DecisionRequest,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> PatchOut:
    access.require(Role.MAINTAINER)
    _need_person(access)
    service = ReviewService(container, session)
    patch = await service.get(access.workspace.id, patch_id)
    patch = await service.approve(access.workspace, access.principal, patch, body.note)
    return await _patch_out(access, container, session, patch)


@router.post("/workspaces/{workspace}/patches/{patch_id}/reject", summary="Reject a proposal")
async def reject(
    patch_id: uuid.UUID,
    body: DecisionRequest,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> PatchOut:
    access.require(Role.MAINTAINER)
    _need_person(access)
    service = ReviewService(container, session)
    patch = await service.get(access.workspace.id, patch_id)
    patch = await service.reject(access.workspace, access.principal, patch, body.note)
    return await _patch_out(access, container, session, patch)


@router.post(
    "/workspaces/{workspace}/patches/{patch_id}/apply",
    summary="Apply an approved patch to a new branch of the repository mirror",
    status_code=status.HTTP_202_ACCEPTED,
)
async def apply(
    patch_id: uuid.UUID,
    body: ApplyRequest,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> PatchOut:
    access.require(Role.MAINTAINER)
    _need_person(access)
    service = ReviewService(container, session)
    patch = await service.get(access.workspace.id, patch_id)
    patch = await service.apply(access.workspace, access.principal, patch, body.branch)
    return await _patch_out(access, container, session, patch)


@router.post(
    "/workspaces/{workspace}/patches/{patch_id}/test-runs",
    summary="Run the repository's tests against the patch",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RunLimit],
)
async def test_patch(
    patch_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> TestRunOut:
    access.require(Role.DEVELOPER)
    patch = await ReviewService(container, session).get(access.workspace.id, patch_id)
    task = await ReviewService(container, session).task_of(patch)
    repository = await ReposRepository(session).get(access.workspace.id, task.repository_id)
    if repository is None:
        raise NotFoundError("Repository not found.")
    run = await TestRunService(container, session).start_for_patch(
        access.workspace, access.principal, repository, patch
    )
    return test_run_out(run, repository.slug, task.number)
