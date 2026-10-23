"""Value sets stored as text with CHECK constraints (cheaper to evolve than Postgres enums)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MAINTAINER = "maintainer"
    DEVELOPER = "developer"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return {Role.VIEWER: 1, Role.DEVELOPER: 2, Role.MAINTAINER: 3, Role.OWNER: 4}[self]

    def allows(self, required: Role) -> bool:
        return self.rank >= required.rank


class RepositorySource(StrEnum):
    GIT = "git"
    ARCHIVE = "archive"


class IndexStatus(StrEnum):
    QUEUED = "queued"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    APPLYING = "applying"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PatchStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    APPLYING = "applying"
    APPLIED = "applied"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self not in {RunStatus.QUEUED, RunStatus.RUNNING}


class RunTrigger(StrEnum):
    MANUAL = "manual"
    AGENT_BASELINE = "agent_baseline"
    AGENT_VERIFY = "agent_verify"
    PATCH = "patch"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class UsageKind(StrEnum):
    ASK = "ask"
    SEARCH = "search"
