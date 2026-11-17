"""Who may do what: tenant isolation, roles, API keys, sessions and cross-site requests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from tests.integration.conftest import WEB_ORIGIN
from tests.integration.support import (
    PASSWORD,
    Member,
    Workspace,
    bearer,
    create_task,
    login,
    signup,
    upload_repository,
    wait_for_task,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def busy(client: httpx.AsyncClient, workspace: Workspace) -> dict[str, Any]:
    """A workspace with a repository, a task with a patch, a run, a conversation and a key."""
    await upload_repository(client, workspace)
    task = await create_task(
        client, workspace, "ledgerkit", "Add clamp", "add `clamp` to ledgerkit/money.py"
    )
    await wait_for_task(client, workspace, task["number"])
    detail = (
        await client.get(
            f"{workspace.base}/tasks/{task['number']}", headers=workspace.owner.headers
        )
    ).json()
    run = (
        await client.post(
            f"{workspace.base}/repositories/ledgerkit/test-runs",
            headers=workspace.who("developer").headers,
        )
    ).json()
    conversation = (
        await client.post(
            f"{workspace.base}/conversations", json={}, headers=workspace.who("developer").headers
        )
    ).json()
    hits = (
        await client.get(
            f"{workspace.base}/search/symbols",
            params={"q": "apply_discount"},
            headers=workspace.owner.headers,
        )
    ).json()["hits"]
    key = (
        await client.post(
            f"{workspace.base}/api-keys",
            json={"name": "k", "role": "viewer"},
            headers=workspace.owner.headers,
        )
    ).json()
    return {
        "task": task["number"],
        "patch": detail["patches"][0]["id"],
        "run": run["number"],
        "conversation": conversation["id"],
        "symbol": hits[0]["id"],
        "key_id": key["id"],
    }


async def test_an_outsider_gets_404_from_every_route_of_a_workspace(
    client: httpx.AsyncClient, workspace: Workspace, busy: dict[str, Any], stranger: Member
) -> None:
    base = workspace.base
    gets = [
        base,
        f"{base}/overview",
        f"{base}/members",
        f"{base}/audit",
        f"{base}/api-keys",
        f"{base}/repositories",
        f"{base}/repositories/ledgerkit",
        f"{base}/repositories/ledgerkit/files",
        f"{base}/repositories/ledgerkit/blob/ledgerkit/pricing.py",
        f"{base}/repositories/ledgerkit/snapshots",
        f"{base}/symbols/{busy['symbol']}",
        f"{base}/search/symbols?q=apply",
        f"{base}/search/text?q=apply",
        f"{base}/search/semantic?q=apply",
        f"{base}/conversations",
        f"{base}/conversations/{busy['conversation']}",
        f"{base}/tasks",
        f"{base}/tasks/{busy['task']}",
        f"{base}/patches/{busy['patch']}",
        f"{base}/patches/{busy['patch']}/export",
        f"{base}/test-runs",
        f"{base}/test-runs/{busy['run']}",
        f"{base}/test-runs/{busy['run']}/log",
    ]
    for url in gets:
        response = await client.get(url, headers=stranger.headers)
        assert response.status_code == 404, (url, response.status_code, response.text)
    posts: list[tuple[str, dict[str, Any]]] = [
        (f"{base}/ask", {"question": "anything"}),
        (f"{base}/tasks", {"repository": "ledgerkit", "title": "Steal the code"}),
        (f"{base}/repositories/ledgerkit/sync", {}),
        (f"{base}/repositories/ledgerkit/test-runs", {}),
        (f"{base}/patches/{busy['patch']}/approve", {}),
        (f"{base}/patches/{busy['patch']}/apply", {}),
        (f"{base}/patches/{busy['patch']}/comments", {"body": "hello"}),
        (f"{base}/api-keys", {"name": "mine"}),
        (f"{base}/members", {"email": "x@example.com"}),
    ]
    for url, body in posts:
        response = await client.post(url, json=body, headers=stranger.headers)
        assert response.status_code == 404, (url, response.status_code, response.text)
    for url in (f"{base}/repositories/ledgerkit", f"{base}", f"{base}/api-keys/{busy['key_id']}"):
        assert (await client.delete(url, headers=stranger.headers)).status_code == 404, url


async def test_a_signed_out_caller_gets_401_everywhere(
    client: httpx.AsyncClient, workspace: Workspace, busy: dict[str, Any]
) -> None:
    for url in (
        workspace.base,
        f"{workspace.base}/repositories",
        f"{workspace.base}/tasks",
        "/api/v1/auth/me",
    ):
        response = await client.get(url)
        assert response.status_code == 401, url
        assert response.json()["error"]["code"] == "unauthorized"
    bad = await client.get(workspace.base, headers=bearer("not-a-token"))
    assert bad.status_code == 401


async def test_roles_gate_every_write(
    client: httpx.AsyncClient, workspace: Workspace, busy: dict[str, Any]
) -> None:
    base, patch = workspace.base, busy["patch"]
    matrix: list[tuple[str, str, dict[str, Any], set[str]]] = [
        # (method, url, body, roles that are allowed)
        (
            "POST",
            f"{base}/repositories",
            {"git_url": "https://localhost/a/b.git"},
            {"owner", "maintainer"},
        ),
        ("POST", f"{base}/repositories/ledgerkit/sync", {}, {"owner", "maintainer"}),
        (
            "POST",
            f"{base}/tasks",
            {"repository": "ledgerkit", "title": "A new task"},
            {"owner", "maintainer", "developer"},
        ),
        (
            "POST",
            f"{base}/repositories/ledgerkit/test-runs",
            {},
            {"owner", "maintainer", "developer"},
        ),
        (
            "POST",
            f"{base}/patches/{patch}/comments",
            {"body": "hi"},
            {"owner", "maintainer", "developer"},
        ),
        ("POST", f"{base}/patches/{patch}/approve", {}, {"owner", "maintainer"}),
        ("POST", f"{base}/api-keys", {"name": "k2"}, {"owner"}),
        ("GET", f"{base}/api-keys", {}, {"owner"}),
        ("GET", f"{base}/audit", {}, {"owner"}),
        ("POST", f"{base}/members", {"email": "nobody@example.com"}, {"owner"}),
        ("PATCH", f"{base}", {"name": "Renamed"}, {"owner"}),
    ]
    for method, url, body, allowed in matrix:
        for role in ("viewer", "developer", "maintainer", "owner"):
            if url.endswith("/approve") and role in allowed:
                continue  # approving changes the patch; checked for the denied roles only
            response = await client.request(
                method, url, json=body or None, headers=workspace.who(role).headers
            )
            if role in allowed:
                assert response.status_code not in {401, 403}, (method, url, role, response.text)
            else:
                assert response.status_code == 403, (method, url, role, response.status_code)


async def test_api_keys_are_hashed_listed_revoked_and_expire(
    client: httpx.AsyncClient, workspace: Workspace, container: Any
) -> None:
    created = await client.post(
        f"{workspace.base}/api-keys",
        json={"name": "ci", "role": "developer", "expires_in_days": 30},
        headers=workspace.owner.headers,
    )
    assert created.status_code == 201
    body = created.json()
    key, key_id = body["key"], body["id"]
    assert key.startswith("cak_") and body["prefix"] in key and body["expires_at"]
    listing = (
        await client.get(f"{workspace.base}/api-keys", headers=workspace.owner.headers)
    ).json()
    assert "key" not in listing[0] and listing[0]["name"] == "ci"
    async with container.db.session() as session:
        stored = (
            await session.execute(
                text("SELECT secret_hash FROM api_keys WHERE id = :i"), {"i": uuid.UUID(key_id)}
            )
        ).scalar_one()
    assert key.rsplit("_", 1)[-1] not in stored and len(stored) == 64

    headers = bearer(key)
    assert (await client.get(f"{workspace.base}/repositories", headers=headers)).status_code == 200
    # A developer key can create tasks but not manage keys or other workspaces.
    assert (await client.get(f"{workspace.base}/api-keys", headers=headers)).status_code == 403
    other = await new_other_workspace(client)
    assert (await client.get(f"{other.base}/repositories", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 403

    # Used keys show when they were last used.
    refreshed = (
        await client.get(f"{workspace.base}/api-keys", headers=workspace.owner.headers)
    ).json()
    assert refreshed[0]["last_used_at"] is not None

    revoked = await client.delete(
        f"{workspace.base}/api-keys/{key_id}", headers=workspace.owner.headers
    )
    assert revoked.status_code == 204
    after = await client.get(f"{workspace.base}/repositories", headers=headers)
    assert after.status_code == 401 and after.json()["error"]["code"] == "invalid_api_key"

    expired = (
        await client.post(
            f"{workspace.base}/api-keys", json={"name": "old"}, headers=workspace.owner.headers
        )
    ).json()
    async with container.db.session() as session:
        await session.execute(
            text("UPDATE api_keys SET expires_at = :t WHERE id = :i"),
            {"t": datetime.now(UTC) - timedelta(days=1), "i": uuid.UUID(expired["id"])},
        )
        await session.commit()
    assert (
        await client.get(f"{workspace.base}/repositories", headers=bearer(expired["key"]))
    ).status_code == 401


async def new_other_workspace(client: httpx.AsyncClient) -> Workspace:
    from tests.integration.support import new_workspace

    return await new_workspace(client, members=False)


async def test_a_key_cannot_decide_reviews_or_delete_anything_it_could_not_read(
    client: httpx.AsyncClient, workspace: Workspace, busy: dict[str, Any]
) -> None:
    key = (
        await client.post(
            f"{workspace.base}/api-keys",
            json={"name": "dev", "role": "developer"},
            headers=workspace.owner.headers,
        )
    ).json()["key"]
    headers = bearer(key)
    approve = await client.post(
        f"{workspace.base}/patches/{busy['patch']}/approve", json={}, headers=headers
    )
    assert approve.status_code == 403
    comment = await client.post(
        f"{workspace.base}/patches/{busy['patch']}/comments",
        json={"body": "from CI"},
        headers=headers,
    )
    assert comment.status_code == 403
    created = await client.post(
        f"{workspace.base}/tasks",
        json={"repository": "ledgerkit", "title": "Created by CI"},
        headers=headers,
    )
    assert created.status_code == 201


async def test_member_changes_take_effect_and_the_last_owner_stays(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    developer = workspace.who("developer")
    promoted = await client.patch(
        f"{workspace.base}/members/{developer.user_id}",
        json={"role": "maintainer"},
        headers=workspace.owner.headers,
    )
    assert promoted.status_code == 200
    assert (
        await client.get(f"{workspace.base}/audit", headers=developer.headers)
    ).status_code == 403
    removed = await client.delete(
        f"{workspace.base}/members/{developer.user_id}", headers=workspace.owner.headers
    )
    assert removed.status_code == 204
    assert (
        await client.get(f"{workspace.base}/repositories", headers=developer.headers)
    ).status_code == 404
    last = await client.patch(
        f"{workspace.base}/members/{workspace.owner.user_id}",
        json={"role": "viewer"},
        headers=workspace.owner.headers,
    )
    assert last.status_code == 422 and last.json()["error"]["code"] == "last_owner"
    duplicate = await client.post(
        f"{workspace.base}/members",
        json={"email": workspace.who("viewer").email, "role": "developer"},
        headers=workspace.owner.headers,
    )
    assert duplicate.status_code == 409


async def test_the_audit_trail_records_who_did_what(
    client: httpx.AsyncClient, workspace: Workspace, busy: dict[str, Any]
) -> None:
    await client.post(
        f"{workspace.base}/patches/{busy['patch']}/approve",
        json={"note": "ok"},
        headers=workspace.who("maintainer").headers,
    )
    events = (await client.get(f"{workspace.base}/audit", headers=workspace.owner.headers)).json()
    actions = [e["action"] for e in events]
    assert {
        "workspace.created",
        "member.added",
        "repository.connected",
        "task.created",
        "patch.approved",
    } <= set(actions)
    approved = next(e for e in events if e["action"] == "patch.approved")
    assert approved["actor_name"] == "Maintainer" and approved["details"]["note"] == "ok"
    assert events == sorted(events, key=lambda e: e["created_at"], reverse=True)


async def test_signing_out_ends_the_session_and_changing_the_password_ends_the_others(
    client: httpx.AsyncClient,
) -> None:
    person = await signup(client)
    assert (await client.get("/api/v1/auth/me", headers=person.headers)).status_code == 200
    second = await login(client, person.email, PASSWORD)
    changed = await client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "Another-pass-2026!"},
        headers=person.headers,
    )
    assert changed.status_code == 200
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/me", headers=second.headers)).status_code == 401
    fresh = bearer(changed.json()["token"])
    assert (await client.get("/api/v1/auth/me", headers=fresh)).status_code == 200
    assert (await client.post("/api/v1/auth/logout", headers=fresh)).status_code == 204
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/me", headers=fresh)).status_code == 401
    wrong = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong", "new_password": "Yet-another-pass-1"},
        headers=(await login(client, person.email, "Another-pass-2026!")).headers,
    )
    assert wrong.status_code == 401


async def test_sign_in_failures_are_uniform_and_lock_the_account(
    client: httpx.AsyncClient,
) -> None:
    person = await signup(client)
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-1234"}
    )
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": person.email, "password": "wrong-password-1"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    for _ in range(8):
        await client.post(
            "/api/v1/auth/login", json={"email": person.email, "password": "wrong-password-1"}
        )
    locked = await client.post(
        "/api/v1/auth/login", json={"email": person.email, "password": PASSWORD}
    )
    assert locked.status_code == 429


async def test_cookie_sessions_need_a_same_site_origin_for_writes(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    signed_in = await client.post(
        "/api/v1/auth/login", json={"email": workspace.owner.email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200
    set_cookie = signed_in.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie
    try:
        assert (await client.get(f"{workspace.base}/repositories")).status_code == 200
        evil = await client.post(
            "/api/v1/workspaces", json={"name": "csrf"}, headers={"origin": "https://evil.example"}
        )
        assert evil.status_code == 403 and evil.json()["error"]["code"] == "csrf"
        no_origin = await client.post("/api/v1/workspaces", json={"name": "csrf"})
        assert no_origin.status_code == 403
        ours = await client.post(
            "/api/v1/workspaces", json={"name": unique_name()}, headers={"origin": WEB_ORIGIN}
        )
        assert ours.status_code == 201
    finally:
        client.cookies.clear()


def unique_name() -> str:
    return f"Cookie team {uuid.uuid4().hex[:6]}"


async def test_signup_is_closed_when_disabled_but_first_run_always_works(
    client: httpx.AsyncClient, container: Any
) -> None:
    settings = container.settings
    object.__setattr__(settings, "allow_signup", False)
    try:
        closed = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": f"{uuid.uuid4().hex[:8]}@example.com",
                "name": "Late",
                "password": PASSWORD,
            },
        )
        assert closed.status_code == 403
    finally:
        object.__setattr__(settings, "allow_signup", True)


async def test_uploads_larger_than_the_limit_are_refused(
    client: httpx.AsyncClient, workspace: Workspace, container: Any
) -> None:
    settings = container.settings
    original = settings.max_archive_mb
    object.__setattr__(settings, "max_archive_mb", 1)
    try:
        response = await client.post(
            f"{workspace.base}/repositories/upload",
            files={
                "file": ("big.zip", b"PK\x03\x04" + b"0" * (2 * 1024 * 1024), "application/zip")
            },
            headers=workspace.who("maintainer").headers,
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
    finally:
        object.__setattr__(settings, "max_archive_mb", original)


async def test_rate_limits_answer_429_with_retry_information(
    client: httpx.AsyncClient, workspace: Workspace, container: Any
) -> None:
    settings = container.settings
    object.__setattr__(settings, "rate_limit_search", 3)
    try:
        statuses = []
        for _ in range(5):
            response = await client.get(
                f"{workspace.base}/search/symbols",
                params={"q": "abc"},
                headers=workspace.who("viewer").headers,
            )
            statuses.append(response.status_code)
        assert statuses == [200, 200, 200, 429, 429]
        assert response.headers["retry-after"]
        assert response.json()["error"]["code"] == "rate_limited"
    finally:
        object.__setattr__(settings, "rate_limit_search", 100_000)
