from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeagent.db.base import Base, IdMixin, TimestampMixin


class Repository(IdMixin, TimestampMixin, Base):
    """A connected codebase. Search and answers always use its current (latest ready) snapshot."""

    __tablename__ = "repositories"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16))
    git_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    current_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("snapshots.id", ondelete="SET NULL", use_alter=True)
    )
    mirror_key: Mapped[str | None] = mapped_column(String(400))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    languages: Mapped[dict[str, Any]] = mapped_column(default=dict)
    file_count: Mapped[int] = mapped_column(default=0)
    symbol_count: Mapped[int] = mapped_column(default=0)
    line_count: Mapped[int] = mapped_column(default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_indexed_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class Snapshot(IdMixin, TimestampMixin, Base):
    """An immutable index of one commit of a repository."""

    __tablename__ = "snapshots"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16))
    # What produced it: "clone", "sync" or "upload", with the uploaded file name if any.
    origin: Mapped[str] = mapped_column(String(16))
    upload_key: Mapped[str | None] = mapped_column(String(400))
    upload_name: Mapped[str | None] = mapped_column(String(300))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    branch: Mapped[str | None] = mapped_column(String(200))
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    indexed_at: Mapped[datetime | None]
