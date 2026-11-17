"""Models and service results rendered as API schemas, in one place."""

from __future__ import annotations

from codeagent.models import Conversation, Message, Patch, Repository, Snapshot, Task, TestRun
from codeagent.repositories.index import EdgeRow
from codeagent.schemas.chat import (
    CitationOut,
    ConversationOut,
    MessageOut,
    SourceOut,
    UsageOut,
)
from codeagent.schemas.repositories import (
    EdgeOut,
    RepositoryDetail,
    RepositoryOut,
    RepositorySettings,
    SnapshotOut,
)
from codeagent.schemas.tasks import FileStatOut, PatchSummary, RunSummary, TaskOut
from codeagent.schemas.test_runs import TestRunOut


def snapshot_out(snapshot: Snapshot | None) -> SnapshotOut | None:
    return SnapshotOut.model_validate(snapshot) if snapshot is not None else None


def repository_out(repository: Repository) -> RepositoryOut:
    return RepositoryOut.model_validate(repository)


def repository_detail(
    repository: Repository,
    current: Snapshot | None,
    latest: Snapshot | None,
    readme_path: str | None,
) -> RepositoryDetail:
    return RepositoryDetail(
        **repository_out(repository).model_dump(),
        settings=RepositorySettings.model_validate(repository.settings or {}),
        current_snapshot=snapshot_out(current),
        latest_snapshot=snapshot_out(latest),
        readme_path=readme_path,
    )


def edge_out(edge: EdgeRow) -> EdgeOut:
    return EdgeOut(
        symbol_id=edge.symbol_id,
        name=edge.name,
        kind=edge.kind,
        path=edge.path,
        line=edge.line,
        is_test=edge.is_test,
    )


def test_run_out(run: TestRun, repository: str, task_number: int | None) -> TestRunOut:
    return TestRunOut(
        id=run.id,
        number=run.number,
        trigger=run.trigger,
        status=run.status,
        total=run.total,
        passed=run.passed,
        failed=run.failed,
        errors=run.errors,
        skipped=run.skipped,
        duration_ms=run.duration_ms,
        backend=run.backend,
        created_at=run.created_at,
        repository_id=run.repository_id,
        repository=repository,
        task_number=task_number,
        patch_id=run.patch_id,
        commit_sha=run.commit_sha,
        command=run.command,
        image=run.image,
        exit_code=run.exit_code,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=[CitationOut.model_validate(c) for c in message.citations or []],
        sources=[SourceOut.model_validate(s) for s in message.sources or []],
        usage=UsageOut.model_validate(message.usage) if message.usage else None,
        created_at=message.created_at,
    )


def conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut.model_validate(conversation)


def run_summary(run: TestRun) -> RunSummary:
    return RunSummary(
        id=run.id,
        number=run.number,
        trigger=run.trigger,
        status=run.status,
        total=run.total,
        passed=run.passed,
        failed=run.failed,
        errors=run.errors,
        skipped=run.skipped,
        duration_ms=run.duration_ms,
        backend=run.backend,
        created_at=run.created_at,
    )


def task_out(task: Task, repository: str, requested_by: str | None) -> TaskOut:
    return TaskOut(
        id=task.id,
        number=task.number,
        repository_id=task.repository_id,
        repository=repository,
        title=task.title,
        status=task.status,
        skill=task.skill,
        planner=task.planner,
        requested_by=requested_by,
        patch_count=task.patch_count,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def patch_summary(patch: Patch) -> PatchSummary:
    return PatchSummary(
        id=patch.id,
        revision=patch.revision,
        status=patch.status,
        summary=patch.summary,
        additions=patch.additions,
        deletions=patch.deletions,
        files=[FileStatOut.model_validate(f) for f in patch.files],
        planner=patch.planner,
        skill=patch.skill,
        created_at=patch.created_at,
        decided_at=patch.decided_at,
        applied_branch=patch.applied_branch,
        applied_commit=patch.applied_commit,
    )
