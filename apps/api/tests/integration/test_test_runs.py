"""Sandboxed test runs: results per test, logs, patch runs and repository settings."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.support import (
    Workspace,
    create_task,
    upload_repository,
    wait_for,
    wait_for_task,
    zip_repository,
)

pytestmark = pytest.mark.integration


async def start_run(
    client: httpx.AsyncClient, workspace: Workspace, repo: str = "ledgerkit"
) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        f"{workspace.base}/repositories/{repo}/test-runs",
        headers=workspace.who("developer").headers,
    )
    assert response.status_code == 202, response.text
    run: dict = response.json()  # type: ignore[type-arg]
    return run


async def finished(client: httpx.AsyncClient, workspace: Workspace, ref: str | int) -> dict:  # type: ignore[type-arg]
    latest: dict = {}  # type: ignore[type-arg]

    async def check() -> bool:
        nonlocal latest
        latest = (
            await client.get(f"{workspace.base}/test-runs/{ref}", headers=workspace.owner.headers)
        ).json()
        return latest["status"] not in {"queued", "running"}

    await wait_for(check, timeout_s=120, what=f"test run {ref}")
    return latest


async def test_a_run_reports_every_test_with_its_outcome(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    queued = await start_run(client, workspace)
    assert queued["status"] == "queued" and queued["trigger"] == "manual"
    run = await finished(client, workspace, queued["number"])
    assert run["status"] == "failed"
    assert (run["total"], run["passed"], run["failed"]) == (32, 31, 1)
    assert run["backend"] == "subprocess" and run["exit_code"] == 1
    failing = [r for r in run["results"] if r["status"] == "failed"]
    assert [r["name"] for r in failing] == ["test_discount_applies_at_threshold"]
    assert failing[0]["file"] == "tests/test_pricing.py"
    assert "assert" in failing[0]["message"]
    assert "1 failed, 31 passed" in run["log_tail"]
    assert run["limits"]["network"] == "none"
    assert run["limits"]["timeout_s"] == 120
    by_id = await client.get(
        f"{workspace.base}/test-runs/{run['id']}", headers=workspace.owner.headers
    )
    assert by_id.json()["number"] == run["number"]
    log = await client.get(
        f"{workspace.base}/test-runs/{run['number']}/log", headers=workspace.owner.headers
    )
    assert log.headers["content-type"].startswith("text/plain")
    assert "test_discount_applies_at_threshold" in log.text


async def test_a_passing_suite_is_passed(client: httpx.AsyncClient, workspace: Workspace) -> None:
    fixed = zip_repository(
        "ledgerkit",
        extra={
            "tests/test_pricing.py": "def test_ok():\n    assert 1 + 1 == 2\n",
        },
    )
    await upload_repository(client, workspace, data=fixed)
    run = await finished(client, workspace, (await start_run(client, workspace))["number"])
    assert run["status"] == "passed" and run["failed"] == 0


async def test_runs_list_and_filter(client: httpx.AsyncClient, workspace: Workspace) -> None:
    await upload_repository(client, workspace)
    first = await start_run(client, workspace)
    await finished(client, workspace, first["number"])
    second = await start_run(client, workspace)
    await finished(client, workspace, second["number"])
    headers = workspace.who("viewer").headers
    listing = (await client.get(f"{workspace.base}/test-runs", headers=headers)).json()
    assert [r["number"] for r in listing["items"]] == [second["number"], first["number"]]
    assert listing["items"][0]["repository"] == "ledgerkit"
    failed = (
        await client.get(
            f"{workspace.base}/test-runs", params={"status": "failed"}, headers=headers
        )
    ).json()
    assert failed["total"] == 2
    none = (
        await client.get(
            f"{workspace.base}/test-runs", params={"status": "passed"}, headers=headers
        )
    ).json()
    assert none["total"] == 0
    page = (
        await client.get(f"{workspace.base}/test-runs", params={"limit": 1}, headers=headers)
    ).json()
    assert len(page["items"]) == 1 and page["total"] == 2


async def test_a_viewer_cannot_start_runs_and_a_repository_can_disable_them(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    denied = await client.post(
        f"{workspace.base}/repositories/ledgerkit/test-runs",
        headers=workspace.who("viewer").headers,
    )
    assert denied.status_code == 403
    updated = await client.patch(
        f"{workspace.base}/repositories/ledgerkit",
        json={"settings": {"test_command": None}},
        headers=workspace.who("maintainer").headers,
    )
    assert updated.status_code == 200, updated.text
    refused = await client.post(
        f"{workspace.base}/repositories/ledgerkit/test-runs",
        headers=workspace.who("developer").headers,
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "no_test_command"


async def test_a_command_that_runs_past_its_limit_is_stopped(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    slow = zip_repository(
        "ledgerkit",
        extra={"tests/test_slow.py": "import time\n\ndef test_slow():\n    time.sleep(60)\n"},
    )
    await upload_repository(client, workspace, data=slow)
    updated = await client.patch(
        f"{workspace.base}/repositories/ledgerkit",
        json={
            "settings": {
                "test_command": "python -m pytest -q tests/test_slow.py",
                "test_timeout_s": 5,
            }
        },
        headers=workspace.who("maintainer").headers,
    )
    assert updated.status_code == 200, updated.text
    run = await finished(client, workspace, (await start_run(client, workspace))["number"])
    assert run["status"] == "timed_out"
    assert "time limit" in run["error"]


async def test_tests_cannot_reach_the_network_or_the_servers_environment(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    probe = (
        "import os, socket\n\n"
        "def test_no_secrets():\n"
        "    assert 'SESSION_SECRET' not in os.environ\n"
        "    assert 'AWS_SECRET_ACCESS_KEY' not in os.environ\n\n"
        "def test_no_network():\n"
        "    try:\n"
        "        socket.create_connection(('93.184.216.34', 80), timeout=2)\n"
        "    except OSError:\n"
        "        return\n"
        "    raise AssertionError('reached the internet')\n"
    )
    data = zip_repository("ledgerkit", extra={"tests/test_probe.py": probe})
    await upload_repository(client, workspace, data=data)
    await client.patch(
        f"{workspace.base}/repositories/ledgerkit",
        json={"settings": {"test_command": "python -m pytest -q tests/test_probe.py"}},
        headers=workspace.who("maintainer").headers,
    )
    run = await finished(client, workspace, (await start_run(client, workspace))["number"])
    assert run["status"] == "passed", run["log_tail"]
    assert run["total"] == 2


async def test_a_patch_can_be_tested_before_it_is_approved(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    task = await create_task(
        client, workspace, "ledgerkit", "Add clamp", "add `clamp` to ledgerkit/pricing.py"
    )
    await wait_for_task(client, workspace, task["number"])
    detail = (
        await client.get(
            f"{workspace.base}/tasks/{task['number']}", headers=workspace.owner.headers
        )
    ).json()
    patch_id = detail["patches"][0]["id"]
    started = await client.post(
        f"{workspace.base}/patches/{patch_id}/test-runs", headers=workspace.who("developer").headers
    )
    assert started.status_code == 202, started.text
    run = await finished(client, workspace, started.json()["number"])
    assert (
        run["trigger"] == "patch"
        and run["patch_id"] == patch_id
        and run["task_number"] == task["number"]
    )
    assert any(r["name"].startswith("test_clamp") for r in run["results"])
    by_task = (
        await client.get(
            f"{workspace.base}/test-runs",
            params={"task": task["number"]},
            headers=workspace.owner.headers,
        )
    ).json()
    assert by_task["total"] >= 3  # baseline, verification and this one
