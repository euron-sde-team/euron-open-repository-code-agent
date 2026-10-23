from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from codeagent.schemas.common import ApiModel, Paged


class RepositorySettings(ApiModel):
    """Per-repository test settings. Limits are capped by the deployment's sandbox limits."""

    test_command: str | None = Field(
        default="python -m pytest -q",
        max_length=500,
        description="Run from the repository root inside the sandbox; empty disables test runs.",
    )
    test_timeout_s: int | None = Field(default=None, ge=5, le=3600)
    memory_mb: int | None = Field(default=None, ge=64, le=16384)


class RepositoryCreate(ApiModel):
    git_url: str = Field(min_length=12, max_length=500, description="HTTPS clone URL.")
    branch: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=120)
    description: str = Field(default="", max_length=1000)


class RepositoryUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    settings: RepositorySettings | None = None


class SnapshotOut(ApiModel):
    id: uuid.UUID
    status: str
    origin: str
    upload_name: str | None
    commit_sha: str | None
    branch: str | None
    stats: dict[str, Any]
    warnings: list[dict[str, Any]]
    error: str | None
    created_at: datetime
    indexed_at: datetime | None


class RepositoryOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    source: str
    git_url: str | None
    default_branch: str | None
    status: str
    error: str | None
    languages: dict[str, Any]
    file_count: int
    symbol_count: int
    line_count: int
    size_bytes: int
    last_indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RepositoryDetail(RepositoryOut):
    settings: RepositorySettings
    current_snapshot: SnapshotOut | None
    latest_snapshot: SnapshotOut | None
    readme_path: str | None


class RepositoryPage(Paged):
    items: list[RepositoryOut]


class FileEntryOut(ApiModel):
    path: str
    language: str
    size_bytes: int
    line_count: int
    is_test: bool
    symbol_count: int
    indexed: bool


class FileListOut(ApiModel):
    snapshot_id: uuid.UUID
    commit_sha: str | None
    files: list[FileEntryOut]


class OutlineSymbol(ApiModel):
    id: uuid.UUID
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    depth: int
    ref_count: int


class BlobOut(ApiModel):
    path: str
    language: str
    size_bytes: int
    line_count: int
    is_test: bool
    indexed: bool
    parse_error: str | None
    commit_sha: str | None
    lines: list[list[tuple[str, str]]] = Field(
        description="Per line, runs of [class, text]; classes are stable highlight names."
    )
    outline: list[OutlineSymbol]


class EdgeOut(ApiModel):
    symbol_id: uuid.UUID | None
    name: str
    kind: str
    path: str
    line: int
    is_test: bool


class SymbolDetail(ApiModel):
    id: uuid.UUID
    name: str
    qualified_name: str
    kind: str
    path: str
    language: str
    start_line: int
    end_line: int
    signature: str
    doc: str
    ref_count: int
    code: list[list[tuple[str, str]]]
    callers: list[EdgeOut]
    callees: list[EdgeOut]
    importers: list[EdgeOut]
    tests: list[EdgeOut]
