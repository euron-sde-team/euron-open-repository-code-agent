"""Routes a queue message to the service that handles it, and keeps the job metrics."""

from __future__ import annotations

import time

from codeagent.core import metrics
from codeagent.core.logging import get_logger
from codeagent.integrations.queue import Job, JobType
from codeagent.services.container import Container
from codeagent.services.indexing import IndexingService
from codeagent.services.review import ReviewService
from codeagent.services.tasks import TaskService
from codeagent.services.test_runs import TestRunService

log = get_logger("codeagent.jobs")


class JobDispatcher:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.indexing = IndexingService(container)

    async def handle(self, job: Job, *, final_attempt: bool = True) -> bool:
        """Run one job. False means "try again later": the message is left on the queue."""
        started = time.perf_counter()
        outcome = "failed"
        try:
            done = await self._run(job, final_attempt)
            outcome = "done" if done else "retry"
            return done
        finally:
            metrics.JOBS.labels(job.type.value, outcome).inc()
            metrics.JOB_DURATION.labels(job.type.value).observe(time.perf_counter() - started)

    async def _run(self, job: Job, final_attempt: bool) -> bool:
        match job.type:
            case JobType.INDEX_SNAPSHOT:
                return await self.indexing.process(job, final_attempt=final_attempt)
            case JobType.RUN_TASK:
                async with self.c.db.session() as session:
                    return await TaskService(self.c, session).run(job)
            case JobType.RUN_TESTS:
                async with self.c.db.session() as session:
                    return await TestRunService(self.c, session).process(job)
            case JobType.APPLY_PATCH:
                async with self.c.db.session() as session:
                    return await ReviewService(self.c, session).process_apply(job)


class Maintenance:
    """The reaper: resend work that a lost message or a crashed worker left stuck."""

    def __init__(self, container: Container) -> None:
        self.c = container

    async def run_once(self) -> dict[str, int]:
        backlog = await self.c.queue.backlog()
        if backlog > self.c.settings.reaper_max_backlog:
            # Resending into a backed-up queue only makes it longer.
            log.info("reaper_skipped", backlog=backlog)
            return {}
        async with self.c.db.session() as session:
            tasks = await TaskService(self.c, session).reap_stale()
        async with self.c.db.session() as session:
            runs = await TestRunService(self.c, session).reap_stale()
        snapshots = await IndexingService(self.c).reap_stale()
        counts = {"snapshots": snapshots, "tasks": tasks, "test_runs": runs}
        if any(counts.values()):
            log.info("reaper_resent", **counts)
        return counts
