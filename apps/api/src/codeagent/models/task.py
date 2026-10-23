"""Tasks, the patch revisions the agent proposes for them, and their review."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeagent.db.base import Base, IdMixin, TimestampMixin


class Task(IdMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE")
    )
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))
    skill: Mapped[str | None] = mapped_column(String(32))
    planner: Mapped[str | None] = mapped_column(String(120))
    base_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("snapshots.id", ondelete="SET NULL")
    )
    base_commit: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    # Timestamped progress notes from the agent run, shown as a timeline in the UI.
    trace: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    usage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    attempts: Mapped[int] = mapped_column(default=0)
    patch_count: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class Patch(IdMixin, TimestampMixin, Base):
    """One revision of the change proposed for a task. Self-contained: it keeps the old and
    new content of every file, so a review never depends on an index that may be pruned."""

    __tablename__ = "patches"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    revision: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(String(300))
    rationale: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    diff: Mapped[str] = mapped_column(Text)
    files: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    additions: Mapped[int] = mapped_column(default=0)
    deletions: Mapped[int] = mapped_column(default=0)
    base_commit: Mapped[str | None] = mapped_column(String(64))
    planner: Mapped[str] = mapped_column(String(120))
    skill: Mapped[str] = mapped_column(String(32))
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_runs.id", ondelete="SET NULL", use_alter=True)
    )
    verify_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_runs.id", ondelete="SET NULL", use_alter=True)
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str | None] = mapped_column(Text)
    applied_branch: Mapped[str | None] = mapped_column(String(200))
    applied_commit: Mapped[str | None] = mapped_column(String(64))
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    applied_at: Mapped[datetime | None]
    apply_error: Mapped[str | None] = mapped_column(Text)


class PatchFile(IdMixin, Base):
    __tablename__ = "patch_files"

    patch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patches.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(1000))
    change_type: Mapped[str] = mapped_column(String(16))
    additions: Mapped[int] = mapped_column(default=0)
    deletions: Mapped[int] = mapped_column(default=0)
    language: Mapped[str] = mapped_column(String(40), default="Text")
    old_content: Mapped[str | None] = mapped_column(Text)
    new_content: Mapped[str | None] = mapped_column(Text)


class ReviewComment(IdMixin, TimestampMixin, Base):
    """A review comment on a patch, optionally anchored to a line of one side of a file."""

    __tablename__ = "review_comments"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    patch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patches.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(String(1000))
    line: Mapped[int | None]
    side: Mapped[str | None] = mapped_column(String(8))
    resolved: Mapped[bool] = mapped_column(default=False)
