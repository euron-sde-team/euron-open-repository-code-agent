"""The demo seed builds a lived-in workspace through the real services."""

from __future__ import annotations

import httpx
import pytest

from codeagent.core.config import Settings
from codeagent.demo.seed import WORKSPACE_SLUG, run
from codeagent.main import create_app
from tests.integration.conftest import (
    AwsResources,
    database_url,
    make_settings,
    recreate_database,
)
from tests.integration.support import bearer

pytestmark = pytest.mark.integration
DEMO_DATABASE = "codeagent_demo_test"
PASSWORD = "Demo-pass-2026-x"


@pytest.fixture(scope="module")
async def demo_settings(aws: AwsResources) -> Settings:
    await recreate_database(DEMO_DATABASE)
    return make_settings(aws, database_url=database_url(DEMO_DATABASE))


async def test_the_seed_creates_every_state_the_screens_show(demo_settings: Settings) -> None:
    summary = await run(demo_settings, password=PASSWORD)
    assert summary.created and summary.workspace == WORKSPACE_SLUG
    assert summary.api_key.startswith("cak_")
    assert [role for _, role, _ in summary.people] == ["owner", "maintainer", "developer", "viewer"]

    app = create_app(demo_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.test", timeout=60
        ) as client:
            login = await client.post(
                "/api/v1/auth/login", json={"email": summary.people[0][0], "password": PASSWORD}
            )
            assert login.status_code == 200
            client.cookies.clear()
            headers = bearer(login.json()["token"])
            base = f"/api/v1/workspaces/{WORKSPACE_SLUG}"
            repos = (await client.get(f"{base}/repositories", headers=headers)).json()
            assert {r["slug"] for r in repos["items"]} == {"ledgerkit", "ratelimit", "checkout-web"}
            assert all(r["status"] == "ready" for r in repos["items"])
            tasks = (await client.get(f"{base}/tasks", headers=headers)).json()
            states = {t["status"] for t in tasks["items"]}
            assert {"awaiting_review", "applied", "rejected", "failed"} <= states
            runs = (await client.get(f"{base}/test-runs", headers=headers)).json()
            assert runs["total"] >= 6
            assert {"manual", "agent_baseline", "agent_verify"} <= {
                r["trigger"] for r in runs["items"]
            }
            overview = (await client.get(f"{base}/overview?days=14", headers=headers)).json()
            totals = overview["totals"]
            assert totals["questions"] >= 6 and totals["searches"] >= 15
            assert totals["open_reviews"] >= 1 and totals["tasks_applied"] == 1
            assert sum(1 for d in overview["daily"] if d["questions"] or d["searches"]) >= 5
            conversations = (
                await client.get(
                    f"{base}/conversations",
                    headers=bearer(
                        (
                            await client.post(
                                "/api/v1/auth/login",
                                json={"email": summary.people[2][0], "password": PASSWORD},
                            )
                        ).json()["token"]
                    ),
                )
            ).json()
            client.cookies.clear()
            assert len(conversations) >= 2
            key_search = await client.get(
                f"{base}/search/symbols", params={"q": "Invoice"}, headers=bearer(summary.api_key)
            )
            assert key_search.status_code == 200 and key_search.json()["hits"]


async def test_seeding_twice_is_a_no_op(demo_settings: Settings) -> None:
    again = await run(demo_settings, password=PASSWORD)
    assert again.created is False
