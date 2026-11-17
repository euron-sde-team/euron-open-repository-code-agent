"""Probes, metrics, the OpenAPI document and the shape of every response."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.support import PASSWORD, Workspace, signup, upload_repository

pytestmark = pytest.mark.integration


async def test_probes_report_the_dependencies(client: httpx.AsyncClient) -> None:
    assert (await client.get("/livez")).json() == {"status": "ok"}
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok", "queue": "ok"},
    }


async def test_metrics_are_prometheus_text_with_route_templates(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    await upload_repository(client, workspace)
    await client.get(f"{workspace.base}/repositories", headers=workspace.owner.headers)
    metrics = (await client.get("/metrics")).text
    assert "codeagent_http_requests_total" in metrics
    assert 'route="/workspaces/{workspace}/repositories"' in metrics
    assert "codeagent_jobs_total" in metrics
    assert workspace.slug not in metrics


async def test_system_info_describes_the_engines_and_limits(client: httpx.AsyncClient) -> None:
    info = (await client.get("/api/v1/system/info")).json()
    assert info["answerer"] == {
        "label": "local",
        "provider": "local",
        "model": None,
        "uses_model": False,
    }
    assert info["embeddings"] == "code-hash-384" and info["embedding_dim"] == 384
    assert info["sandbox"]["network"] == "none"
    assert {"rename", "fix_test", "add_function"} == set(info["skills"])
    assert "clamp" in info["helpers"]
    assert info["max_archive_mb"] == 100


async def test_first_run_setup_is_reported_until_an_account_exists(
    client: httpx.AsyncClient,
) -> None:
    await signup(client)
    assert (await client.get("/api/v1/system/info")).json()["needs_setup"] is False


async def test_every_response_has_a_request_id_and_errors_use_the_envelope(
    client: httpx.AsyncClient,
) -> None:
    ok = await client.get("/livez", headers={"x-request-id": "trace-me-1"})
    assert ok.headers["x-request-id"] == "trace-me-1"
    missing = await client.get("/api/v1/nope")
    assert missing.status_code == 404
    error = missing.json()["error"]
    assert error["code"] == "not_found" and error["request_id"] == missing.headers["x-request-id"]
    invalid = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": ""}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "who@example.com", "password": PASSWORD}
    )
    assert wrong.status_code == 401


async def test_cors_allows_the_web_app_and_nobody_else(client: httpx.AsyncClient) -> None:
    allowed = await client.options(
        "/api/v1/auth/login",
        headers={"origin": "http://localhost:3190", "access-control-request-method": "POST"},
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3190"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = await client.options(
        "/api/v1/auth/login",
        headers={"origin": "https://evil.example", "access-control-request-method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers


async def test_the_openapi_document_describes_every_route(client: httpx.AsyncClient) -> None:
    document = (await client.get("/openapi.json")).json()
    paths = document["paths"]
    assert len(paths) >= 45
    for path, operations in paths.items():
        assert path.startswith("/api/v1/"), path
        for method, operation in operations.items():
            assert operation.get("summary"), (method, path)
            assert operation.get("tags"), (method, path)
    assert "/api/v1/workspaces/{workspace}/ask/stream" in paths
    assert "\N{EM DASH}" not in str(document) and "\N{EN DASH}" not in str(document)
    schemes = set(document.get("components", {}).get("schemas", {}))
    assert {"TaskDetail", "PatchOut", "BlobOut", "SystemInfo", "OverviewOut"} <= schemes
