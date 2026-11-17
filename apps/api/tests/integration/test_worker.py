"""The worker and the reaper over a real SQS queue (the Floci emulator)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from codeagent.core.config import Settings
from codeagent.main import create_app
from codeagent.services.container import Container
from codeagent.services.jobs import Maintenance
from codeagent.worker import Worker
from tests.integration.conftest import AwsResources, make_settings
from tests.integration.support import (
    new_workspace,
    upload_repository,
    wait_for,
    wait_for_repository,
    zip_repository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def queued(
    aws: AwsResources, settings: Settings
) -> AsyncIterator[tuple[httpx.AsyncClient, Container]]:
    """An API whose jobs go to SQS, with no worker running yet."""
    sqs_settings = make_settings(
        aws, queue_backend="sqs", worker_poll_wait_s=1, worker_concurrency=2
    )
    app = create_app(sqs_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.test", timeout=60
        ) as http:
            yield http, app.state.container


@contextlib.asynccontextmanager
async def running(container: Container) -> AsyncIterator[Worker]:
    worker = Worker(container, container.queue)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run())
    try:
        yield worker
    finally:
        worker.stop()
        await asyncio.wait_for(task, 60)


async def test_a_worker_indexes_a_repository_from_the_queue(
    queued: tuple[httpx.AsyncClient, Container],
) -> None:
    client, container = queued
    workspace = await new_workspace(client)
    await upload_repository(client, workspace, wait=False)
    async with running(container):
        repository = await wait_for_repository(client, workspace, "ledgerkit")
    assert repository["file_count"] == 15
    # The message was deleted once the job recorded its outcome.
    assert await container.queue.backlog() == 0  # type: ignore[union-attr]


async def test_the_reaper_resends_a_job_whose_message_was_lost(
    queued: tuple[httpx.AsyncClient, Container],
) -> None:
    client, container = queued
    workspace = await new_workspace(client)
    lost: list[Any] = []

    async def drop(job: Any) -> None:
        lost.append(job)

    original = container.queue.enqueue
    container.queue.enqueue = drop  # type: ignore[method-assign]
    try:
        response = await client.post(
            f"{workspace.base}/repositories/upload",
            files={"file": ("ledgerkit.zip", zip_repository("ledgerkit"), "application/zip")},
            headers=workspace.who("maintainer").headers,
        )
        assert response.status_code == 201
    finally:
        container.queue.enqueue = original  # type: ignore[method-assign]
    assert len(lost) == 1
    async with container.db.session() as session:
        await session.execute(
            text("UPDATE snapshots SET updated_at = :t WHERE workspace_id = :w"),
            {"t": datetime.now(UTC) - timedelta(minutes=30), "w": uuid.UUID(workspace.id)},
        )
        await session.commit()
    repository = (
        await client.get(
            f"{workspace.base}/repositories/ledgerkit", headers=workspace.owner.headers
        )
    ).json()
    assert repository["status"] == "queued"

    resent = await Maintenance(container).run_once()
    assert resent["snapshots"] >= 1
    async with running(container):
        ready = await wait_for_repository(client, workspace, "ledgerkit")
    assert ready["file_count"] == 15


async def test_the_reaper_waits_while_the_queue_is_backed_up(
    queued: tuple[httpx.AsyncClient, Container],
) -> None:
    _, container = queued
    original = container.queue.backlog

    async def busy() -> int:
        return container.settings.reaper_max_backlog + 1

    container.queue.backlog = busy  # type: ignore[method-assign]
    try:
        assert await Maintenance(container).run_once() == {}
    finally:
        container.queue.backlog = original  # type: ignore[method-assign]


async def test_a_job_that_asks_to_be_retried_stays_on_the_queue(
    queued: tuple[httpx.AsyncClient, Container], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, container = queued
    workspace = await new_workspace(client)
    calls: list[bool] = []

    async def handle(self: Any, job: Any, *, final_attempt: bool = True) -> bool:
        calls.append(final_attempt)
        return len(calls) > 1

    from codeagent.services.jobs import JobDispatcher

    monkeypatch.setattr(JobDispatcher, "handle", handle)
    await upload_repository(client, workspace, wait=False)
    worker = Worker(container, container.queue)  # type: ignore[arg-type]
    settings = container.settings
    object.__setattr__(settings, "job_timeout_s", 30)
    task = asyncio.create_task(worker.run())
    try:
        # Not deleted on the first attempt: SQS shows it again after the visibility timeout.
        async def twice() -> bool:
            return len(calls) >= 1

        await wait_for(twice, timeout_s=20, what="the first attempt")
        assert calls[0] is False
    finally:
        worker.stop()
        await asyncio.wait_for(task, 120)
    object.__setattr__(settings, "job_timeout_s", 300)
