"""Tasks, the agent, review, apply and export, with real sandboxed test runs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.integration.support import (
    Workspace,
    create_task,
    upload_repository,
    wait_for,
    wait_for_task,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def repo(client: httpx.AsyncClient, workspace: Workspace) -> Workspace:
    await upload_repository(client, workspace, "ledgerkit")
    return workspace


async def patch_of(
    client: httpx.AsyncClient, workspace: Workspace, task: dict[str, Any]
) -> dict[str, Any]:
    detail = (
        await client.get(
            f"{workspace.base}/tasks/{task['number']}", headers=workspace.owner.headers
        )
    ).json()
    current = next(p for p in detail["patches"] if p["status"] == "proposed")
    response = await client.get(
        f"{workspace.base}/patches/{current['id']}", headers=workspace.owner.headers
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def decide(
    client: httpx.AsyncClient,
    workspace: Workspace,
    patch: dict[str, Any],
    verb: str,
    *,
    role: str = "maintainer",
    note: str | None = None,
) -> httpx.Response:
    return await client.post(
        f"{workspace.base}/patches/{patch['id']}/{verb}",
        json={"note": note} if verb != "apply" else {},
        headers=workspace.who(role).headers,
    )


async def test_the_failing_test_is_fixed_by_a_verified_mutation(
    client: httpx.AsyncClient, repo: Workspace
) -> None:
    task = await create_task(
        client,
        repo,
        "ledgerkit",
        "Fix the failing pricing test",
        "test_discount_applies_at_threshold fails. Fix the failing test.",
    )
    done = await wait_for_task(client, repo, task["number"])
    assert done["status"] == "awaiting_review", done.get("error")
    assert done["skill"] == "fix_test" and done["planner"] == "local"
    assert any("Proposed revision 1" in event["message"] for event in done["trace"])

    patch = await patch_of(client, repo, task)
    assert patch["revision"] == 1 and patch["skill"] == "fix_test"
    assert [f["path"] for f in patch["files"]] == ["ledgerkit/pricing.py"]
    lines = patch["diff_files"][0]["hunks"][0]["lines"]
    removed = next(line for line in lines if line["kind"] == "del")
    added = next(line for line in lines if line["kind"] == "add")
    assert "subtotal.amount > threshold.amount" in "".join(t for _, t in removed["tokens"])
    assert "subtotal.amount >= threshold.amount" in "".join(t for _, t in added["tokens"])
    assert patch["baseline_run"]["failed"] == 1
    assert patch["verify_run"]["status"] == "passed" and patch["verify_run"]["failed"] == 0
    assert patch["rationale"] and patch["plan"]
    assert patch["decision_note"] is None


async def test_review_comment_approve_apply_and_export(
    client: httpx.AsyncClient, repo: Workspace, tmp_path: Path
) -> None:
    task = await create_task(
        client, repo, "ledgerkit", "Add safe_divide", "add `safe_divide` to ledgerkit/pricing.py"
    )
    done = await wait_for_task(client, repo, task["number"])
    assert done["status"] == "awaiting_review", done.get("error")
    assert done["skill"] == "add_function"
    patch = await patch_of(client, repo, task)
    assert {f["path"] for f in patch["files"]} == {"ledgerkit/pricing.py", "tests/test_pricing.py"}
    assert patch["verify_run"]["status"] == "failed"  # the sample's one known failing test remains
    assert patch["verify_run"]["passed"] > patch["baseline_run"]["passed"]

    # A developer can comment on a line; a viewer cannot.
    commented = await client.post(
        f"{repo.base}/patches/{patch['id']}/comments",
        json={
            "body": "Please also cover negative numbers.",
            "path": "ledgerkit/pricing.py",
            "line": 40,
            "side": "new",
        },
        headers=repo.who("developer").headers,
    )
    assert commented.status_code == 201, commented.text
    assert commented.json()["author"] == "Developer"
    denied = await client.post(
        f"{repo.base}/patches/{patch['id']}/comments",
        json={"body": "nope"},
        headers=repo.who("viewer").headers,
    )
    assert denied.status_code == 403
    unknown_file = await client.post(
        f"{repo.base}/patches/{patch['id']}/comments",
        json={"body": "x", "path": "not/in/patch.py", "line": 1},
        headers=repo.who("developer").headers,
    )
    assert unknown_file.status_code == 404
    resolved = await client.patch(
        f"{repo.base}/comments/{commented.json()['id']}",
        json={"resolved": True},
        headers=repo.who("maintainer").headers,
    )
    assert resolved.json()["resolved"] is True

    # Only a maintainer decides; an unapproved patch cannot be applied.
    assert (await decide(client, repo, patch, "approve", role="developer")).status_code == 403
    assert (await decide(client, repo, patch, "apply")).status_code == 409
    approved = await decide(client, repo, patch, "approve", note="Looks right.")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decision_note"] == "Looks right."
    assert approved.json()["decided_by"] == "Maintainer"
    assert (await decide(client, repo, patch, "reject")).status_code == 409

    applied = await decide(client, repo, patch, "apply")
    assert applied.status_code == 202, applied.text

    async def is_applied() -> bool:
        current = (
            await client.get(f"{repo.base}/patches/{patch['id']}", headers=repo.owner.headers)
        ).json()
        return bool(current["status"] == "applied")

    await wait_for(is_applied, what="the patch to be applied")
    final = (
        await client.get(f"{repo.base}/patches/{patch['id']}", headers=repo.owner.headers)
    ).json()
    assert final["applied_branch"].startswith(f"codeagent/{task['number']}-add-safe-divide")
    assert len(final["applied_commit"]) == 40
    assert (
        await client.get(f"{repo.base}/tasks/{task['number']}", headers=repo.owner.headers)
    ).json()["status"] == "applied"

    # The export is a real git mbox: it applies with `git am` to the original tree.
    exported = await client.get(
        f"{repo.base}/patches/{patch['id']}/export",
        params={"format": "patch"},
        headers=repo.owner.headers,
    )
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    work = tmp_path / "tree"
    work.mkdir()
    from tests.conftest import REPOS

    subprocess.run(["cp", "-R", f"{REPOS / 'ledgerkit'}/.", str(work)], check=True)
    for cmd in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "base"],
    ):
        subprocess.run(["git", *cmd], cwd=work, check=True, capture_output=True)
    (work / "change.patch").write_text(exported.text)
    am = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "am", "change.patch"],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert am.returncode == 0, am.stderr
    assert "def safe_divide" in (work / "ledgerkit" / "pricing.py").read_text()
    plain = await client.get(
        f"{repo.base}/patches/{patch['id']}/export",
        params={"format": "diff"},
        headers=repo.owner.headers,
    )
    assert plain.text.startswith("diff --git")


async def test_a_rename_updates_every_use_and_the_suite_outcome_is_unchanged(
    client: httpx.AsyncClient, repo: Workspace
) -> None:
    task = await create_task(
        client,
        repo,
        "ledgerkit",
        "Rename it",
        "rename `apply_discount` to `apply_threshold_discount`",
    )
    done = await wait_for_task(client, repo, task["number"])
    assert done["status"] == "awaiting_review", done.get("error")
    patch = await patch_of(client, repo, task)
    paths = {f["path"] for f in patch["files"]}
    assert {"ledgerkit/pricing.py", "ledgerkit/invoice.py", "tests/test_pricing.py"} <= paths
    assert patch["baseline_run"]["failed"] == patch["verify_run"]["failed"] == 1
    assert patch["baseline_run"]["passed"] == patch["verify_run"]["passed"]


async def test_independent_review_stops_the_requester_from_approving(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await client.patch(
        f"{workspace.base}",
        json={"settings": {"require_independent_review": True}},
        headers=workspace.owner.headers,
    )
    await upload_repository(client, workspace, "ledgerkit", as_role="maintainer")
    task = await create_task(
        client,
        workspace,
        "ledgerkit",
        "Add clamp",
        "add `clamp` to ledgerkit/pricing.py",
        as_role="maintainer",
    )
    await wait_for_task(client, workspace, task["number"])
    patch = await patch_of(client, workspace, task)
    detail = (
        await client.get(
            f"{workspace.base}/tasks/{task['number']}", headers=workspace.who("maintainer").headers
        )
    ).json()
    assert detail["can_approve"] is False
    blocked = await decide(client, workspace, patch, "approve", role="maintainer")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "independent_review_required"
    other = (
        await client.get(
            f"{workspace.base}/tasks/{task['number']}", headers=workspace.owner.headers
        )
    ).json()
    assert other["can_approve"] is True
    assert (await decide(client, workspace, patch, "approve", role="owner")).status_code == 200


async def test_a_rejected_task_can_be_retried_into_a_new_revision(
    client: httpx.AsyncClient, repo: Workspace
) -> None:
    task = await create_task(
        client, repo, "ledgerkit", "Add clamp", "add `clamp` to ledgerkit/money.py"
    )
    await wait_for_task(client, repo, task["number"])
    first = await patch_of(client, repo, task)
    rejected = await decide(client, repo, first, "reject", note="Wrong module.")
    assert rejected.json()["status"] == "rejected"
    retried = await client.post(
        f"{repo.base}/tasks/{task['number']}/retry",
        json={"description": "add `clamp` to ledgerkit/pricing.py"},
        headers=repo.who("developer").headers,
    )
    assert retried.status_code == 200, retried.text
    done = await wait_for_task(client, repo, task["number"], until={"awaiting_review", "failed"})
    assert done["status"] == "awaiting_review"
    assert [p["status"] for p in done["patches"]] == ["proposed", "rejected"]
    assert done["patches"][0]["revision"] == 2
    second = await patch_of(client, repo, task)
    assert second["files"][0]["path"] == "ledgerkit/pricing.py"


async def test_a_request_the_offline_planner_cannot_do_fails_with_guidance(
    client: httpx.AsyncClient, repo: Workspace
) -> None:
    task = await create_task(
        client, repo, "ledgerkit", "Make invoices prettier", "Improve the layout."
    )
    done = await wait_for_task(client, repo, task["number"])
    assert done["status"] == "failed"
    assert done["error_code"] == "unsupported"
    assert "LLM_PROVIDER" in done["error"]
    assert done["patches"] == []


async def test_roles_decide_who_can_create_and_cancel_tasks(
    client: httpx.AsyncClient, repo: Workspace
) -> None:
    denied = await client.post(
        f"{repo.base}/tasks",
        json={"repository": "ledgerkit", "title": "A viewer asks"},
        headers=repo.who("viewer").headers,
    )
    assert denied.status_code == 403
    missing = await client.post(
        f"{repo.base}/tasks",
        json={"repository": "nope", "title": "Nothing to change"},
        headers=repo.who("developer").headers,
    )
    assert missing.status_code == 404
    short = await client.post(
        f"{repo.base}/tasks",
        json={"repository": "ledgerkit", "title": "x"},
        headers=repo.who("developer").headers,
    )
    assert short.status_code == 422
    listing = (await client.get(f"{repo.base}/tasks", headers=repo.who("viewer").headers)).json()
    assert listing["total"] == 0


async def test_tasks_list_filters_and_paginates(client: httpx.AsyncClient, repo: Workspace) -> None:
    first = await create_task(
        client, repo, "ledgerkit", "Add clamp", "add `clamp` to ledgerkit/money.py"
    )
    second = await create_task(client, repo, "ledgerkit", "Make it pretty", "Improve the layout.")
    await wait_for_task(client, repo, first["number"])
    await wait_for_task(client, repo, second["number"])
    headers = repo.who("viewer").headers
    everything = (await client.get(f"{repo.base}/tasks", headers=headers)).json()
    assert everything["total"] == 2
    assert [t["number"] for t in everything["items"]] == [second["number"], first["number"]]
    failed = (
        await client.get(f"{repo.base}/tasks", params={"status": "failed"}, headers=headers)
    ).json()
    assert [t["title"] for t in failed["items"]] == ["Make it pretty"]
    open_ = (
        await client.get(f"{repo.base}/tasks", params={"status": "open"}, headers=headers)
    ).json()
    assert [t["title"] for t in open_["items"]] == ["Add clamp"]
    page = (
        await client.get(f"{repo.base}/tasks", params={"limit": 1, "offset": 1}, headers=headers)
    ).json()
    assert page["total"] == 2 and page["items"][0]["number"] == first["number"]
    searched = (
        await client.get(f"{repo.base}/tasks", params={"q": "clamp"}, headers=headers)
    ).json()
    assert searched["total"] == 1


async def test_a_queued_task_can_be_cancelled_and_numbers_never_repeat(
    client: httpx.AsyncClient, repo: Workspace, container: Any
) -> None:
    from codeagent.integrations.queue import InlineQueue

    queue = container.queue
    assert isinstance(queue, InlineQueue)
    handler, queue._handler = queue._handler, None
    try:
        queue._handler = _hold  # jobs are accepted and do nothing, so the task stays queued
        task = await create_task(
            client, repo, "ledgerkit", "Add clamp", "add `clamp` to ledgerkit/money.py"
        )
        assert task["status"] == "queued"
        cancelled = await client.post(
            f"{repo.base}/tasks/{task['number']}/cancel", headers=repo.who("developer").headers
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        again = await client.post(
            f"{repo.base}/tasks/{task['number']}/cancel", headers=repo.who("developer").headers
        )
        assert again.status_code == 409
    finally:
        await queue.drain()
        queue._handler = handler
    nxt = await create_task(
        client, repo, "ledgerkit", "Add clamp again", "add `clamp` to ledgerkit/money.py"
    )
    assert nxt["number"] == task["number"] + 1


async def _hold(job: Any) -> bool:
    return True
