"""Review: the diff, comments, approve or reject, apply to a branch, export.

Nothing changes a repository without approval. `apply` refuses a patch that is not
approved, and the worker checks again under a row lock before it touches the mirror.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from codeagent import __version__
from codeagent.agent.diffs import parse_patch
from codeagent.codeintel.highlight import highlight_lines
from codeagent.core.errors import ConflictError, ForbiddenError, NotFoundError
from codeagent.core.logging import get_logger
from codeagent.integrations import git
from codeagent.integrations.queue import Job, JobType
from codeagent.integrations.storage import mirror_key
from codeagent.models import Patch, PatchFile, Repository, ReviewComment, Task, User, Workspace
from codeagent.models.enums import PatchStatus, Role, TaskStatus
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.tasks import PatchRepository, TaskRepository
from codeagent.repositories.users import UserRepository
from codeagent.schemas.workspaces import WorkspaceSettings
from codeagent.services import audit
from codeagent.services.container import Container
from codeagent.services.locks import repository_lock
from codeagent.services.principal import Principal
from codeagent.services.workspaces import slugify
from codeagent.services.worktree import restore_mirror, store_mirror

log = get_logger("codeagent.review")
Tokens = list[tuple[str, str]]


@dataclass(slots=True)
class DiffFileView:
    path: str
    change_type: str
    language: str
    additions: int
    deletions: int
    hunks: list[dict[str, Any]]


def _tokens(lines: list[Tokens], number: int | None, text: str) -> Tokens:
    if number is not None and 0 < number <= len(lines):
        return lines[number - 1]
    return [("", text)] if text else []


def diff_view(patch: Patch, files: list[PatchFile]) -> list[DiffFileView]:
    """The patch as files, hunks and lines, each line with syntax tokens from its own side."""
    by_path = {f.path: f for f in files}
    views = []
    for parsed in parse_patch(patch.diff):
        stored = by_path.get(parsed.path)
        language = stored.language if stored else "Text"
        old = highlight_lines(stored.old_content or "", language, parsed.path) if stored else []
        new = highlight_lines(stored.new_content or "", language, parsed.path) if stored else []
        hunks = [
            {
                "old_start": hunk.old_start,
                "old_count": hunk.old_count,
                "new_start": hunk.new_start,
                "new_count": hunk.new_count,
                "section": hunk.section,
                "lines": [
                    {
                        "kind": line.kind,
                        "old_line": line.old_line,
                        "new_line": line.new_line,
                        "tokens": _tokens(new, line.new_line, line.text)
                        if line.kind == "add"
                        else _tokens(old, line.old_line, line.text),
                    }
                    for line in hunk.lines
                ],
            }
            for hunk in parsed.hunks
        ]
        views.append(
            DiffFileView(
                parsed.path, parsed.change_type, language, parsed.additions, parsed.deletions, hunks
            )
        )
    return views


def branch_name(task: Task) -> str:
    slug = slugify(task.title)[:40].strip("-") or "change"
    return f"codeagent/{task.number}-{slug}"


def commit_message(task: Task, patch: Patch, requester: User | None, approver: User | None) -> str:
    body = re.sub(r"\n{3,}", "\n\n", patch.rationale.strip())
    trailers = [f"CodeAgent-Task: #{task.number}", f"CodeAgent-Revision: {patch.revision}"]
    if requester is not None:
        trailers.append(f"Requested-by: {requester.name} <{requester.email}>")
    if approver is not None:
        trailers.append(f"Approved-by: {approver.name} <{approver.email}>")
    return f"{task.title}\n\n{body}\n\n" + "\n".join(trailers) + "\n"


def mbox(task: Task, patch: Patch, message: str) -> str:
    """The patch as an mbox message that `git am` applies with the rationale as its body."""
    subject, _, body = message.partition("\n\n")
    stat_lines = [
        f" {f['path']} | {f['additions'] + f['deletions']} "
        f"{'+' * min(f['additions'], 30)}{'-' * min(f['deletions'], 30)}"
        for f in patch.files
    ]
    files_changed = len(patch.files)
    summary = (
        f" {files_changed} file{'s' if files_changed != 1 else ''} changed, "
        f"{patch.additions} insertion{'s' if patch.additions != 1 else ''}(+), "
        f"{patch.deletions} deletion{'s' if patch.deletions != 1 else ''}(-)"
    )
    commit = patch.applied_commit or "0" * 40
    date = format_datetime(patch.created_at or datetime.now(UTC))
    return (
        f"From {commit} Mon Sep 17 00:00:00 2001\n"
        f"From: {git.BOT_NAME} <{git.BOT_EMAIL}>\n"
        f"Date: {date}\n"
        f"Subject: [PATCH] {subject}\n\n"
        f"{body.rstrip()}\n---\n"
        + "\n".join(stat_lines)
        + f"\n{summary}\n\n{patch.diff}-- \ncodeagent {__version__}\n\n"
    )


class ReviewService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.patches = PatchRepository(session)
        self.tasks = TaskRepository(session)

    async def get(self, workspace_id: uuid.UUID, patch_id: uuid.UUID) -> Patch:
        patch = await self.patches.get(workspace_id, patch_id)
        if patch is None:
            raise NotFoundError("Patch not found.")
        return patch

    async def task_of(self, patch: Patch) -> Task:
        task = await self.tasks.get(patch.workspace_id, patch.task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        return task

    async def files(self, patch: Patch) -> list[PatchFile]:
        return await self.patches.files(patch.id)

    async def comments(self, patch: Patch) -> list[tuple[ReviewComment, str | None]]:
        return await self.patches.comments(patch.id)

    async def add_comment(
        self,
        workspace: Workspace,
        principal: Principal,
        patch: Patch,
        *,
        body: str,
        path: str | None,
        line: int | None,
        side: str | None,
    ) -> ReviewComment:
        if principal.user is None:
            raise ForbiddenError("Comments need a signed-in person.")
        if path is not None and path not in {f["path"] for f in patch.files}:
            raise NotFoundError("That file is not part of the patch.")
        comment = await self.patches.add_comment(
            ReviewComment(
                workspace_id=workspace.id,
                patch_id=patch.id,
                author_id=principal.user.id,
                body=body.strip(),
                path=path,
                line=line if path else None,
                side=(side or "new") if path and line else None,
            )
        )
        await self.session.commit()
        return comment

    async def update_comment(
        self,
        workspace: Workspace,
        principal: Principal,
        role: Role,
        comment_id: uuid.UUID,
        *,
        body: str | None,
        resolved: bool | None,
    ) -> ReviewComment:
        comment = await self.patches.comment(workspace.id, comment_id)
        if comment is None:
            raise NotFoundError("Comment not found.")
        is_author = comment.author_id is not None and comment.author_id == principal.user_id
        if body is not None:
            if not is_author:
                raise ForbiddenError("Only the author can edit a comment.")
            comment.body = body.strip()
        if resolved is not None:
            if not (is_author or role.allows(Role.MAINTAINER)):
                raise ForbiddenError("Only the author or a maintainer can resolve a comment.")
            comment.resolved = resolved
        await self.session.commit()
        return comment

    async def delete_comment(
        self, workspace: Workspace, principal: Principal, role: Role, comment_id: uuid.UUID
    ) -> None:
        comment = await self.patches.comment(workspace.id, comment_id)
        if comment is None:
            raise NotFoundError("Comment not found.")
        if comment.author_id != principal.user_id and not role.allows(Role.OWNER):
            raise ForbiddenError("Only the author or an owner can delete a comment.")
        await self.session.delete(comment)
        await self.session.commit()

    async def _decide(
        self,
        workspace: Workspace,
        principal: Principal,
        patch: Patch,
        approve: bool,
        note: str | None,
    ) -> Patch:
        locked = await self.patches.get_for_update(workspace.id, patch.id)
        if locked is None:
            raise NotFoundError("Patch not found.")
        if locked.status != PatchStatus.PROPOSED:
            raise ConflictError(
                f"This revision is {locked.status}; only a proposed revision can be decided."
            )
        task = await self.tasks.get_for_update(workspace.id, locked.task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        settings = WorkspaceSettings.model_validate(workspace.settings or {})
        if settings.require_independent_review and task.created_by == principal.user_id:
            raise ForbiddenError(
                "This workspace requires an independent review: the requester cannot approve or "
                "reject their own task.",
                code="independent_review_required",
            )
        now = datetime.now(UTC)
        locked.status = PatchStatus.APPROVED if approve else PatchStatus.REJECTED
        locked.decided_by = principal.user_id
        locked.decided_at = now
        locked.decision_note = (note or "").strip() or None
        task.status = TaskStatus.APPROVED if approve else TaskStatus.REJECTED
        verb = "approved" if approve else "rejected"
        await self.tasks.append_trace(
            task.id,
            {
                "at": now.isoformat(),
                "message": f"Revision {locked.revision} {verb}.",
                "kind": "review",
            },
        )
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action=f"patch.{verb}",
            target_type="patch",
            target_id=locked.id,
            details={
                "task": task.number,
                "revision": locked.revision,
                "note": locked.decision_note,
            },
        )
        await self.session.commit()
        return locked

    async def approve(
        self, workspace: Workspace, principal: Principal, patch: Patch, note: str | None
    ) -> Patch:
        return await self._decide(workspace, principal, patch, True, note)

    async def reject(
        self, workspace: Workspace, principal: Principal, patch: Patch, note: str | None
    ) -> Patch:
        return await self._decide(workspace, principal, patch, False, note)

    async def apply(
        self, workspace: Workspace, principal: Principal, patch: Patch, branch: str | None
    ) -> Patch:
        locked = await self.patches.get_for_update(workspace.id, patch.id)
        if locked is None:
            raise NotFoundError("Patch not found.")
        if locked.status != PatchStatus.APPROVED:
            raise ConflictError("Only an approved patch can be applied.", code="not_approved")
        task = await self.tasks.get_for_update(workspace.id, locked.task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        locked.status = PatchStatus.APPLYING
        locked.applied_branch = git.validate_branch(branch) if branch else branch_name(task)
        locked.applied_by = principal.user_id
        locked.apply_error = None
        task.status = TaskStatus.APPLYING
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="patch.apply_requested",
            target_type="patch",
            target_id=locked.id,
            details={"task": task.number, "branch": locked.applied_branch},
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job(JobType.APPLY_PATCH, workspace.id, locked.id))
        return locked

    async def process_apply(self, job: Job) -> bool:
        """Worker: create the branch, apply and commit, store the mirror. Approval re-checked."""
        async with self.c.db.session() as session:
            patches, tasks = PatchRepository(session), TaskRepository(session)
            patch = await patches.get(job.workspace_id, job.target_id)
            if patch is None or patch.status != PatchStatus.APPLYING:
                return True  # applied already, or the request was superseded
            task = await tasks.get(job.workspace_id, patch.task_id)
            repository = (
                await ReposRepository(session).get(job.workspace_id, task.repository_id)
                if task
                else None
            )
            if task is None or repository is None:
                return True
            users = UserRepository(session)
            requester = await users.get(task.created_by) if task.created_by else None
            approver = await users.get(patch.decided_by) if patch.decided_by else None
            message = commit_message(task, patch, requester, approver)
            session.expunge_all()

        try:
            sha, branch = await self._commit(repository, task, patch, message)
        except (git.GitError, Exception) as exc:
            detail = (
                exc.message if isinstance(exc, git.GitError) else "The patch could not be applied."
            )
            log.warning("apply_failed", patch_id=str(patch.id), error=detail)
            await self._apply_failed(job, detail)
            return True

        async with self.c.db.session() as session:
            patches, tasks = PatchRepository(session), TaskRepository(session)
            current = await patches.get_for_update(job.workspace_id, job.target_id)
            current_task = await tasks.get_for_update(job.workspace_id, patch.task_id)
            if current is None or current_task is None:
                return True
            now = datetime.now(UTC)
            current.status = PatchStatus.APPLIED
            current.applied_branch = branch
            current.applied_commit = sha
            current.applied_at = now
            current_task.status = TaskStatus.APPLIED
            await tasks.append_trace(
                current_task.id,
                {
                    "at": now.isoformat(),
                    "message": f"Applied to branch {branch} as {sha[:12]}.",
                    "kind": "success",
                },
            )
            await audit.record(
                session,
                workspace_id=job.workspace_id,
                principal=None,
                action="patch.applied",
                target_type="patch",
                target_id=current.id,
                details={"task": current_task.number, "branch": branch, "commit": sha},
            )
            await session.commit()
        return True

    async def _commit(
        self, repository: Repository, task: Task, patch: Patch, message: str
    ) -> tuple[str, str]:
        branch = patch.applied_branch or branch_name(task)
        key = repository.mirror_key or mirror_key(repository.workspace_id, repository.id)
        async with repository_lock(self.c.redis, repository.id):
            with git.scratch_dir("apply") as scratch:
                local = Path(scratch) / "tree"
                await restore_mirror(self.c.storage, repository, local)
                if await git.branch_exists(local, branch):
                    branch = f"{branch}-r{patch.revision}"
                start = patch.base_commit or "HEAD"
                sha = await git.commit_on_branch(
                    local, branch=branch, start=start, patch=patch.diff, message=message
                )
                # Leave the mirror on its default branch, so later syncs and indexing see it.
                head_branch = repository.default_branch or "main"
                if await git.branch_exists(local, head_branch):
                    await git.git("checkout", "--quiet", "--force", head_branch, cwd=local)
                await store_mirror(self.c.storage, repository, local, key)
        return sha, branch

    async def _apply_failed(self, job: Job, message: str) -> None:
        async with self.c.db.session() as session:
            patches, tasks = PatchRepository(session), TaskRepository(session)
            patch = await patches.get_for_update(job.workspace_id, job.target_id)
            if patch is None:
                return
            patch.status = PatchStatus.APPROVED
            patch.apply_error = message
            task = await tasks.get_for_update(job.workspace_id, patch.task_id)
            if task is not None:
                task.status = TaskStatus.APPROVED
                await tasks.append_trace(
                    task.id,
                    {"at": datetime.now(UTC).isoformat(), "message": message, "kind": "error"},
                )
            await session.commit()

    async def export(self, patch: Patch, fmt: str) -> tuple[str, str, str]:
        task = await self.task_of(patch)
        users = UserRepository(self.session)
        requester = await users.get(task.created_by) if task.created_by else None
        approver = await users.get(patch.decided_by) if patch.decided_by else None
        stem = f"codeagent-task-{task.number}-r{patch.revision}"
        if fmt == "patch":
            message = commit_message(task, patch, requester, approver)
            return f"{stem}.patch", "text/x-patch; charset=utf-8", mbox(task, patch, message)
        return f"{stem}.diff", "text/x-diff; charset=utf-8", patch.diff
