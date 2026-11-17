"""The worker: indexing, agent runs, test runs and patch application, from SQS.

    python -m codeagent.worker

- Jobs run with bounded concurrency. A message is deleted once the job has recorded its
  outcome; a job that asks to be retried is left on the queue and reappears after the
  visibility timeout, and SQS moves it to the dead-letter queue after three receives.
- While a job runs, the worker extends its message's visibility, so a long indexing run is
  not delivered a second time.
- The reaper runs every MAINTENANCE_INTERVAL_S on one worker at a time (a Valkey lock).
- SIGTERM stops receiving, lets running jobs finish (their hand-back window), then exits.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket

from prometheus_client import start_http_server

from codeagent.core.config import get_settings
from codeagent.core.logging import configure_logging, get_logger
from codeagent.db.migrate import migrate
from codeagent.integrations.queue import ReceivedJob, SqsQueue
from codeagent.services.container import Container, build_container
from codeagent.services.jobs import JobDispatcher, Maintenance

log = get_logger("codeagent.worker")
SHUTDOWN_GRACE_S = 120
REAPER_LOCK = "lock:reaper"
MAX_RECEIVES = 3


class Worker:
    def __init__(self, container: Container, queue: SqsQueue | None) -> None:
        self.c = container
        self.queue = queue
        self.dispatcher = JobDispatcher(container)
        self.maintenance = Maintenance(container)
        self.concurrency = container.settings.worker_concurrency
        self.identity = f"{socket.gethostname()}:{os.getpid()}"
        self.stopping = asyncio.Event()
        self.inflight: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        if not self.stopping.is_set():
            log.info("worker_stopping", inflight=len(self.inflight))
            self.stopping.set()

    async def run(self) -> None:
        reaper = asyncio.create_task(self._reaper_loop())
        try:
            if self.queue is not None:
                await self._receive_loop(self.queue)
            else:
                await self.stopping.wait()
        finally:
            if self.inflight:
                await asyncio.wait(self.inflight, timeout=SHUTDOWN_GRACE_S)
            reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper

    async def _receive_loop(self, queue: SqsQueue) -> None:
        settings = self.c.settings
        while not self.stopping.is_set():
            free = self.concurrency - len(self.inflight)
            if free <= 0:
                await asyncio.wait(self.inflight, return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                received = await queue.receive(
                    max_messages=min(10, free),
                    wait_s=settings.worker_poll_wait_s,
                    visibility_s=settings.worker_visibility_s,
                )
            except Exception:
                log.exception("queue_receive_failed")
                await asyncio.sleep(5)
                continue
            for item in received:
                task = asyncio.create_task(self._handle(queue, item))
                self.inflight.add(task)
                task.add_done_callback(self.inflight.discard)

    async def _keep_alive(self, queue: SqsQueue, item: ReceivedJob) -> None:
        visibility = self.c.settings.worker_visibility_s
        while True:
            await asyncio.sleep(visibility / 2)
            try:
                await queue.extend(item.receipt, visibility)
            except Exception:
                log.warning("visibility_extend_failed", job=item.job.type.value)
                return

    async def _handle(self, queue: SqsQueue, item: ReceivedJob) -> None:
        keep_alive = asyncio.create_task(self._keep_alive(queue, item))
        try:
            done = await self.dispatcher.handle(
                item.job, final_attempt=item.receive_count >= MAX_RECEIVES
            )
            if done:
                await queue.delete(item.receipt)
        except Exception:
            # Leave the message: it becomes visible again and is retried, then dead-lettered.
            log.exception(
                "job_failed", job_type=item.job.type.value, target=str(item.job.target_id)
            )
        finally:
            keep_alive.cancel()

    async def _reaper_loop(self) -> None:
        interval = self.c.settings.maintenance_interval_s
        while not self.stopping.is_set():
            try:
                leader = await self.c.redis.set(
                    REAPER_LOCK, self.identity.encode(), ex=max(5, interval - 5), nx=True
                )
                if leader:
                    await self.maintenance.run_once()
            except Exception:
                log.exception("reaper_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=interval)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.migrate_on_boot:
        await migrate(settings)
    container = build_container(settings)
    queue = container.queue if isinstance(container.queue, SqsQueue) else None
    if queue is None:
        log.info("worker_reaper_only", reason="QUEUE_BACKEND is not sqs")
    if port := int(os.environ.get("WORKER_METRICS_PORT", "0")):
        start_http_server(port)
    worker = Worker(container, queue)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    log.info("worker_started", concurrency=worker.concurrency, queue=settings.queue_backend)
    try:
        await worker.run()
    finally:
        await container.close()
        log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
