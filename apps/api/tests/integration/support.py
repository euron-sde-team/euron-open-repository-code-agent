"""Small HTTP helpers shared by the integration tests."""

from __future__ import annotations

import asyncio
import io
import time
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from tests.conftest import REPOS

PASSWORD = "Integration-pass-2026"


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class Member:
    email: str
    user_id: str
    token: str
    role: str

    @property
    def headers(self) -> dict[str, str]:
        return bearer(self.token)


@dataclass
class Workspace:
    id: str
    slug: str
    owner: Member
    members: dict[str, Member] = field(default_factory=dict)

    @property
    def base(self) -> str:
        return f"/api/v1/workspaces/{self.slug}"

    def who(self, role: str) -> Member:
        return self.owner if role == "owner" else self.members[role]


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def signup(client: httpx.AsyncClient, name: str = "Test Person") -> Member:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    response = await client.post(
        "/api/v1/auth/signup", json={"email": email, "name": name, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    # Bearer tokens only: a cookie left in the shared client would authenticate later calls.
    client.cookies.clear()
    body = response.json()
    return Member(email, body["user"]["id"], body["token"], "owner")


async def login(client: httpx.AsyncClient, email: str, password: str) -> Member:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return Member(email, body["user"]["id"], body["token"], "")


async def new_workspace(client: httpx.AsyncClient, *, members: bool = True) -> Workspace:
    owner = await signup(client, "Owner Person")
    response = await client.post(
        "/api/v1/workspaces", json={"name": unique("Team")}, headers=owner.headers
    )
    assert response.status_code == 201, response.text
    created = response.json()
    workspace = Workspace(created["id"], created["slug"], owner)
    if members:
        for role in ("maintainer", "developer", "viewer"):
            workspace.members[role] = await add_member(client, workspace, role)
    return workspace


async def add_member(client: httpx.AsyncClient, workspace: Workspace, role: str) -> Member:
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    added = await client.post(
        f"{workspace.base}/members",
        json={"email": email, "name": role.title(), "role": role},
        headers=workspace.owner.headers,
    )
    assert added.status_code == 201, added.text
    member = await login(client, email, added.json()["temporary_password"])
    return Member(member.email, member.user_id, member.token, role)


def zip_repository(name: str, *, extra: dict[str, str] | None = None) -> bytes:
    """A bundled sample repository as a zip, optionally with extra or replaced files."""
    root = REPOS / name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(root).as_posix()
                if extra and relative in extra:
                    continue
                archive.write(path, f"{name}/{relative}")
        for relative, content in (extra or {}).items():
            archive.writestr(f"{name}/{relative}", content)
    return buffer.getvalue()


async def wait_for(
    check: Callable[[], Awaitable[bool]], *, timeout_s: float = 60, what: str = "condition"
) -> None:
    deadline = time.monotonic() + timeout_s
    while not await check():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.1)


async def upload_repository(
    client: httpx.AsyncClient,
    workspace: Workspace,
    name: str = "ledgerkit",
    *,
    data: bytes | None = None,
    wait: bool = True,
    as_role: str = "maintainer",
) -> dict[str, Any]:
    response = await client.post(
        f"{workspace.base}/repositories/upload",
        files={"file": (f"{name}.zip", data or zip_repository(name), "application/zip")},
        data={"name": name},
        headers=workspace.who(as_role).headers,
    )
    assert response.status_code == 201, response.text
    repository: dict[str, Any] = response.json()
    if wait:
        repository = await wait_for_repository(client, workspace, repository["slug"])
    return repository


async def wait_for_repository(
    client: httpx.AsyncClient, workspace: Workspace, slug: str, *, status: str = "ready"
) -> dict[str, Any]:
    latest: dict[str, Any] = {}

    async def check() -> bool:
        nonlocal latest
        response = await client.get(
            f"{workspace.base}/repositories/{slug}", headers=workspace.owner.headers
        )
        assert response.status_code == 200, response.text
        latest = response.json()
        assert latest["status"] != "failed" or status == "failed", latest.get("error")
        return bool(latest["status"] == status)

    await wait_for(check, what=f"repository {slug} to be {status}")
    return latest


async def wait_for_task(
    client: httpx.AsyncClient, workspace: Workspace, number: int, *, until: set[str] | None = None
) -> dict[str, Any]:
    done = until or {"awaiting_review", "failed", "approved", "applied", "rejected", "cancelled"}
    latest: dict[str, Any] = {}

    async def check() -> bool:
        nonlocal latest
        response = await client.get(
            f"{workspace.base}/tasks/{number}", headers=workspace.owner.headers
        )
        assert response.status_code == 200, response.text
        latest = response.json()
        return str(latest["status"]) in done

    await wait_for(check, timeout_s=180, what=f"task #{number}")
    return latest


async def create_task(
    client: httpx.AsyncClient,
    workspace: Workspace,
    repository: str,
    title: str,
    description: str = "",
    *,
    as_role: str = "developer",
) -> dict[str, Any]:
    response = await client.post(
        f"{workspace.base}/tasks",
        json={"repository": repository, "title": title, "description": description},
        headers=workspace.who(as_role).headers,
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created
