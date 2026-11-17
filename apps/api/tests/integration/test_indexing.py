"""Connecting a repository: upload, index in the background, browse what was indexed."""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from tests.integration.support import (
    Workspace,
    upload_repository,
    wait_for,
    wait_for_repository,
    zip_repository,
)

pytestmark = pytest.mark.integration


async def test_an_uploaded_archive_is_indexed(client: httpx.AsyncClient, workspace: Workspace) -> None:
    repository = await upload_repository(client, workspace)
    assert repository["status"] == "ready"
    assert repository["file_count"] == 15
    assert repository["symbol_count"] > 50
    assert "Python" in repository["languages"]
    assert repository["current_snapshot"]["status"] == "ready"
    assert repository["current_snapshot"]["stats"]["indexed_files"] == 15
    assert repository["readme_path"] == "README.md"


async def test_the_file_tree_and_a_highlighted_file_with_its_outline(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    base = f"{workspace.base}/repositories/ledgerkit"
    files = (await client.get(f"{base}/files", headers=workspace.owner.headers)).json()
    paths = {f["path"] for f in files["files"]}
    assert {"ledgerkit/pricing.py", "tests/test_pricing.py", "README.md"} <= paths
    blob = await client.get(f"{base}/blob/ledgerkit/pricing.py", headers=workspace.owner.headers)
    assert blob.status_code == 200
    body = blob.json()
    assert body["language"] == "Python"
    assert len(body["lines"]) == body["line_count"]
    flat = [css for line in body["lines"] for css, _ in line]
    assert "kw" in flat
    names = {(s["name"], s["kind"], s["depth"]) for s in body["outline"]}
    assert ("apply_discount", "function", 0) in names
    rendered = "\n".join("".join(text for _, text in line) for line in body["lines"])
    assert "def apply_discount(" in rendered


async def test_a_symbol_shows_its_callers_callees_and_tests(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    hits = (
        await client.get(
            f"{workspace.base}/search/symbols", params={"q": "apply_discount"}, headers=workspace.owner.headers
        )
    ).json()["hits"]
    symbol_id = next(h["id"] for h in hits if h["name"] == "apply_discount")
    detail = (
        await client.get(f"{workspace.base}/symbols/{symbol_id}", headers=workspace.owner.headers)
    ).json()
    assert detail["path"] == "ledgerkit/pricing.py"
    assert "def apply_discount" in "".join(t for line in detail["code"] for _, t in line)
    assert any(c["path"] == "ledgerkit/invoice.py" for c in detail["callers"])
    assert any(t["path"] == "tests/test_pricing.py" for t in detail["tests"])
    assert detail["ref_count"] >= 5


async def test_a_second_upload_creates_a_new_snapshot_and_swaps_it_in(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    first = await upload_repository(client, workspace)
    base = f"{workspace.base}/repositories/ledgerkit"
    changed = zip_repository("ledgerkit", extra={"ledgerkit/extra.py": "def brand_new_helper():\n    return 1\n"})
    response = await client.post(
        f"{base}/upload",
        files={"file": ("ledgerkit-v2.zip", changed, "application/zip")},
        headers=workspace.members["maintainer"].headers,
    )
    assert response.status_code == 202, response.text
    async def second_is_current() -> bool:
        detail = (await client.get(base, headers=workspace.owner.headers)).json()
        return bool(detail["current_snapshot"]["id"] != first["current_snapshot"]["id"])

    await wait_for(second_is_current, what="the new snapshot to become current")
    detail = (await client.get(base, headers=workspace.owner.headers)).json()
    assert detail["file_count"] == 16
    history = (await client.get(f"{base}/snapshots", headers=workspace.owner.headers)).json()
    assert len(history) == 2 and all(s["status"] == "ready" for s in history)
    found = (
        await client.get(
            f"{workspace.base}/search/symbols", params={"q": "brand_new_helper"}, headers=workspace.owner.headers
        )
    ).json()["hits"]
    assert found and found[0]["path"] == "ledgerkit/extra.py"


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("notes.txt", b"just text", 415),
        ("empty.zip", b"", 422),
    ],
)
async def test_bad_uploads_are_refused_with_the_error_envelope(
    client: httpx.AsyncClient, workspace: Workspace, filename: str, content: bytes, status: int
) -> None:
    response = await client.post(
        f"{workspace.base}/repositories/upload",
        files={"file": (filename, content, "application/octet-stream")},
        headers=workspace.members["maintainer"].headers,
    )
    assert response.status_code == status, response.text
    assert response.json()["error"]["request_id"]


async def test_a_damaged_or_hostile_archive_fails_indexing_with_a_reason(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../escape.py", "x = 1\n")
    for name, content, reason in (
        ("evil", buffer.getvalue(), "outside its root"),
        ("broken", b"PK\x03\x04 not really a zip", "damaged"),
    ):
        repository = await upload_repository(client, workspace, name, data=content, wait=False)
        failed = await wait_for_repository(client, workspace, repository["slug"], status="failed")
        assert reason in failed["error"]
        assert failed["file_count"] == 0


async def test_git_urls_are_validated_before_anything_is_queued(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    headers = workspace.members["maintainer"].headers
    for url in (
        "http://github.com/a/b.git",
        "https://user:pw@github.com/a/b.git",
        "https://localhost/a/b.git",
        "https://169.254.169.254/latest/meta-data",
    ):
        response = await client.post(
            f"{workspace.base}/repositories", json={"git_url": url}, headers=headers
        )
        assert response.status_code == 422, (url, response.text)


async def test_deleting_a_repository_removes_its_index(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    base = f"{workspace.base}/repositories/ledgerkit"
    assert (await client.delete(base, headers=workspace.members["maintainer"].headers)).status_code == 204
    assert (await client.get(base, headers=workspace.owner.headers)).status_code == 404
    hits = (
        await client.get(
            f"{workspace.base}/search/symbols", params={"q": "apply_discount"}, headers=workspace.owner.headers
        )
    ).json()["hits"]
    assert hits == []


async def test_repository_names_are_unique_slugs_and_lists_paginate(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace, "ledgerkit", wait=False)
    await upload_repository(client, workspace, "ratelimit", wait=False)
    await wait_for_repository(client, workspace, "ledgerkit")
    await wait_for_repository(client, workspace, "ratelimit")
    page = (
        await client.get(
            f"{workspace.base}/repositories", params={"limit": 1}, headers=workspace.owner.headers
        )
    ).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1
    second = (
        await client.get(
            f"{workspace.base}/repositories", params={"limit": 1, "offset": 1}, headers=workspace.owner.headers
        )
    ).json()
    assert second["items"][0]["slug"] != page["items"][0]["slug"]
    filtered = (
        await client.get(
            f"{workspace.base}/repositories", params={"q": "rate"}, headers=workspace.owner.headers
        )
    ).json()
    assert [r["slug"] for r in filtered["items"]] == ["ratelimit"]
