"""Symbol, text and semantic search against a real index."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.integration.support import Workspace, upload_repository

pytestmark = pytest.mark.integration


@pytest.fixture
async def indexed(client: httpx.AsyncClient, workspace: Workspace) -> Workspace:
    await upload_repository(client, workspace, "ledgerkit", wait=False)
    await upload_repository(client, workspace, "ratelimit", wait=False)
    from tests.integration.support import wait_for_repository

    await wait_for_repository(client, workspace, "ledgerkit")
    await wait_for_repository(client, workspace, "ratelimit")
    return workspace


async def search(
    client: httpx.AsyncClient, workspace: Workspace, mode: str, **params: Any
) -> dict[str, Any]:
    response = await client.get(
        f"{workspace.base}/search/{mode}", params=params, headers=workspace.who("viewer").headers
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_symbol_search_ranks_exact_then_prefix_then_fuzzy(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    exact = (await search(client, indexed, "symbols", q="apply_discount"))["hits"]
    assert exact[0]["name"] == "apply_discount"
    assert exact[0]["path"] == "ledgerkit/pricing.py"
    assert (exact[0]["start_line"], exact[0]["end_line"]) == (18, 24)
    prefix = (await search(client, indexed, "symbols", q="vol"))["hits"]
    assert all(h["name"].lower().startswith("vol") for h in prefix[:2])
    assert "volume_discount" in {h["name"] for h in prefix}
    fuzzy = (await search(client, indexed, "symbols", q="aply_discont"))["hits"]
    assert any(h["name"] == "apply_discount" for h in fuzzy)


async def test_symbol_search_filters_by_kind_and_repository(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    classes = (await search(client, indexed, "symbols", q="Invoice", kind="class"))["hits"]
    assert classes and all(h["kind"] == "class" for h in classes)
    go = (await search(client, indexed, "symbols", q="Bucket", repository="ratelimit"))["hits"]
    assert go and all(h["repository"] == "ratelimit" for h in go)
    only_py = (await search(client, indexed, "symbols", q="Bucket", repository="ledgerkit"))["hits"]
    assert only_py == []
    bad = await client.get(
        f"{indexed.base}/search/symbols",
        params={"q": "x", "kind": "nonsense"},
        headers=indexed.owner.headers,
    )
    assert bad.status_code == 422


async def test_text_search_finds_lines_with_match_ranges(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    result = await search(client, indexed, "text", q="volume_discount")
    assert result["match_count"] >= 3 and not result["truncated"]
    by_path = {f["path"]: f for f in result["files"]}
    assert "ledgerkit/pricing.py" in by_path
    first = by_path["ledgerkit/pricing.py"]["matches"][0]
    assert "volume_discount" in first["text"]
    start, end = first["ranges"][0]
    assert first["text"][start:end].lower() == "volume_discount"


async def test_text_search_supports_regex_path_globs_and_case(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    regex = await search(client, indexed, "text", q=r"def (calc|rate)_\w+", regex="true")
    assert {f["path"] for f in regex["files"]} == {"ledgerkit/tax.py"}
    scoped = await search(client, indexed, "text", q="Decimal", path="ledgerkit/*.py")
    assert scoped["files"] and all(f["path"].startswith("ledgerkit/") for f in scoped["files"])
    sensitive = await search(client, indexed, "text", q="DECIMAL", case_sensitive="true")
    assert sensitive["match_count"] == 0
    insensitive = await search(client, indexed, "text", q="DECIMAL")
    assert insensitive["match_count"] > 0


async def test_text_search_refuses_dangerous_or_pointless_patterns(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    for params in (
        {"q": "(a+)+$", "regex": "true"},
        {"q": "(unclosed", "regex": "true"},
        {"q": "x"},
    ):
        response = await client.get(
            f"{indexed.base}/search/text", params=params, headers=indexed.owner.headers
        )
        assert response.status_code == 422, (params, response.text)
        assert response.json()["error"]["code"] in {
            "unsafe_regex",
            "invalid_regex",
            "validation_failed",
        }


async def test_text_search_results_are_capped(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    result = await search(client, indexed, "text", q="de", limit=5)
    assert result["match_count"] <= 5
    assert result["truncated"] is True


async def test_semantic_search_matches_meaning_not_just_words(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    result = await search(client, indexed, "semantic", q="how is sales tax worked out for a region")
    assert result["hits"]
    top = result["hits"][0]
    assert top["path"] == "ledgerkit/tax.py"
    assert top["vector_score"] is not None or top["keyword_score"] is not None
    assert 1 <= top["start_line"] <= top["end_line"]
    limiter = await search(client, indexed, "semantic", q="limit requests per client")
    assert limiter["hits"][0]["repository"] == "ratelimit"


async def test_searches_are_scoped_to_the_workspace(
    client: httpx.AsyncClient, indexed: Workspace, stranger: Any
) -> None:
    other = await client.get(
        f"{indexed.base}/search/symbols", params={"q": "apply_discount"}, headers=stranger.headers
    )
    assert other.status_code == 404
    outsider = await client.post(
        "/api/v1/workspaces", json={"name": "Elsewhere"}, headers=stranger.headers
    )
    elsewhere = outsider.json()["slug"]
    empty = await client.get(
        f"/api/v1/workspaces/{elsewhere}/search/symbols",
        params={"q": "apply_discount"},
        headers=stranger.headers,
    )
    assert empty.json()["hits"] == []


async def test_search_activity_is_counted_for_the_dashboard(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    await search(client, indexed, "symbols", q="Invoice")
    overview = (await client.get(f"{indexed.base}/overview", headers=indexed.owner.headers)).json()
    assert overview["totals"]["searches"] >= 1
    assert overview["totals"]["repositories"] == 2
    assert overview["totals"]["repositories_ready"] == 2
    assert len(overview["daily"]) == 14
