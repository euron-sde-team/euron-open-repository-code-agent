from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from codeagent.schemas.common import ApiModel

RoleName = Literal["owner", "maintainer", "developer", "viewer"]


class WorkspaceSettings(ApiModel):
    """How the agent and the review flow behave in this workspace."""

    require_independent_review: bool = Field(
        default=False,
        description="The person who requested a task cannot approve its patch.",
    )
    agent_mode: Literal["auto", "local"] = Field(
        default="auto",
        description="auto uses the configured model if any; local never calls a model.",
    )
    run_baseline_tests: bool = Field(
        default=True,
        description="Run the tests on the base commit before the agent changes anything.",
    )


class WorkspaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class WorkspaceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    settings: WorkspaceSettings | None = None


class WorkspaceOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    settings: WorkspaceSettings
    role: str
    created_at: datetime


class MemberOut(ApiModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: str
    joined_at: datetime


class MemberAdd(ApiModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=120)
    role: RoleName = "developer"


class MemberAdded(ApiModel):
    member: MemberOut
    temporary_password: str | None = Field(
        default=None, description="Set only when the account was created by this call. Shown once."
    )


class MemberUpdate(ApiModel):
    role: RoleName
