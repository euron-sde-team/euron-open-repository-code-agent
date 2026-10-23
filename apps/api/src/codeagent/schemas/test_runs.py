from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from codeagent.schemas.common import ApiModel, Paged
from codeagent.schemas.tasks import RunSummary


class TestRunOut(RunSummary):
    __test__ = False

    repository_id: uuid.UUID
    repository: str
    task_number: int | None
    patch_id: uuid.UUID | None
    commit_sha: str | None
    command: str
    image: str | None
    exit_code: int | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class TestRunPage(Paged):
    __test__ = False

    items: list[TestRunOut]


class TestCaseOut(ApiModel):
    __test__ = False

    name: str
    classname: str
    status: str
    duration_ms: int
    message: str
    file: str | None
    line: int | None


class TestRunDetail(TestRunOut):
    __test__ = False

    limits: dict[str, Any]
    results: list[TestCaseOut]
    log_tail: str
    log_truncated: bool
    has_full_log: bool
