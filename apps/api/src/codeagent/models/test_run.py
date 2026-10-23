from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeagent.db.base import Base, IdMixin, TimestampMixin


class TestRun(IdMixin, TimestampMixin, Base):
    """One sandboxed run of a repository's tests, on a snapshot or on a patched tree."""

    __tablename__ = "test_runs"
    __test__ = False  # not a pytest test class, despite the name

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE")
    )
    number: Mapped[int]
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("snapshots.id", ondelete="SET NULL")
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patches.id", ondelete="SET NULL")
    )
    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    command: Mapped[str] = mapped_column(Text)
    backend: Mapped[str | None] = mapped_column(String(16))
    image: Mapped[str | None] = mapped_column(String(200))
    limits: Mapped[dict[str, Any]] = mapped_column(default=dict)
    exit_code: Mapped[int | None]
    duration_ms: Mapped[int | None]
    total: Mapped[int] = mapped_column(default=0)
    passed: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    results: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    log_tail: Mapped[str] = mapped_column(Text, default="")
    log_key: Mapped[str | None] = mapped_column(String(400))
    log_truncated: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
