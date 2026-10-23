from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from codeagent.schemas.common import ApiModel, Paged


class TaskCreate(ApiModel):
    repository: str = Field(description="Repository id or slug.")
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=8000)


class TaskRetry(ApiModel):
    description: str | None = Field(
        default=None, max_length=8000, description="Replace the description before retrying."
    )


class TraceEvent(ApiModel):
    at: datetime
    message: str
    kind: str


class PlanStepOut(ApiModel):
    title: str
    detail: str = ""


class FileStatOut(ApiModel):
    path: str
    change_type: str
    additions: int
    deletions: int


class RunSummary(ApiModel):
    id: uuid.UUID
    number: int
    trigger: str
    status: str
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: int | None
    backend: str | None
    created_at: datetime


class PatchSummary(ApiModel):
    id: uuid.UUID
    revision: int
    status: str
    summary: str
    additions: int
    deletions: int
    files: list[FileStatOut]
    planner: str
    skill: str
    created_at: datetime
    decided_at: datetime | None
    applied_branch: str | None
    applied_commit: str | None


class TaskOut(ApiModel):
    id: uuid.UUID
    number: int
    repository_id: uuid.UUID
    repository: str
    title: str
    status: str
    skill: str | None
    planner: str | None
    requested_by: str | None
    patch_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskPage(Paged):
    items: list[TaskOut]


class TaskDetail(TaskOut):
    description: str
    base_commit: str | None
    error_code: str | None
    trace: list[TraceEvent]
    usage: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    patches: list[PatchSummary]
    runs: list[RunSummary]
    can_approve: bool = Field(
        description="Whether the caller may approve or reject the current patch."
    )


class DiffLineOut(ApiModel):
    kind: Literal["context", "add", "del"]
    old_line: int | None
    new_line: int | None
    tokens: list[tuple[str, str]]


class HunkOut(ApiModel):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str
    lines: list[DiffLineOut]


class PatchFileOut(ApiModel):
    path: str
    change_type: str
    language: str
    additions: int
    deletions: int
    hunks: list[HunkOut]


class CommentOut(ApiModel):
    id: uuid.UUID
    author: str | None
    author_id: uuid.UUID | None
    body: str
    path: str | None
    line: int | None
    side: str | None
    resolved: bool
    created_at: datetime


class PatchOut(PatchSummary):
    task_id: uuid.UUID
    task_number: int
    rationale: str
    plan: list[PlanStepOut]
    base_commit: str | None
    decision_note: str | None
    decided_by: str | None
    applied_at: datetime | None
    apply_error: str | None
    diff_files: list[PatchFileOut]
    comments: list[CommentOut]
    baseline_run: RunSummary | None
    verify_run: RunSummary | None


class CommentCreate(ApiModel):
    body: str = Field(min_length=1, max_length=8000)
    path: str | None = Field(default=None, max_length=1000)
    line: int | None = Field(default=None, ge=1)
    side: Literal["old", "new"] | None = None


class CommentUpdate(ApiModel):
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    resolved: bool | None = None


class DecisionRequest(ApiModel):
    note: str | None = Field(default=None, max_length=4000)


class ApplyRequest(ApiModel):
    branch: str | None = Field(
        default=None, max_length=200, description="Defaults to codeagent/<number>-<slug>."
    )
