from __future__ import annotations

import uuid
from datetime import datetime

from codeagent.schemas.common import ApiModel


class OverviewTotals(ApiModel):
    repositories: int
    repositories_ready: int
    files: int
    symbols: int
    lines: int
    open_reviews: int
    tasks: int
    tasks_applied: int
    tasks_failed: int
    approval_rate: float
    test_runs: int
    test_pass_rate: float
    median_run_ms: int
    questions: int
    searches: int
    model_tokens: int
    median_review_hours: float | None


class DayPoint(ApiModel):
    day: str
    runs_passed: int
    runs_failed: int
    questions: int
    searches: int


class ActivityItem(ApiModel):
    kind: str
    title: str
    detail: str
    status: str
    href: str
    at: datetime
    actor: str | None


class TaskStatusCount(ApiModel):
    status: str
    count: int


class OverviewOut(ApiModel):
    days: int
    totals: OverviewTotals
    daily: list[DayPoint]
    tasks_by_status: list[TaskStatusCount]
    recent: list[ActivityItem]
    workspace_id: uuid.UUID
