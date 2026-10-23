"""The job queue: SQS (with a dead-letter queue) in deployments, in-process otherwise.

Messages carry a job type and ids only. The worker re-reads the rows it is told about, so a
duplicated or stale message is harmless: every handler checks the current state first and
does nothing when the work is already done.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import anyio
import orjson

from codeagent.core.config import Settings
from codeagent.core.logging import get_logger
from codeagent.integrations import aws

log = get_logger("codeagent.queue")


class JobType(StrEnum):
    INDEX_SNAPSHOT = "index_snapshot"
    RUN_TASK = "run_task"
    RUN_TESTS = "run_tests"
    APPLY_PATCH = "apply_patch"


@dataclass(frozen=True, slots=True)
class Job:
    type: JobType
    workspace_id: uuid.UUID
    target_id: uuid.UUID

    def encode(self) -> str:
        return orjson.dumps(
            {
                "type": self.type.value,
                "workspace_id": str(self.workspace_id),
                "target_id": str(self.target_id),
            }
        ).decode()

    @classmethod
    def decode(cls, body: str) -> Job:
        data = orjson.loads(body)
        return cls(
            JobType(data["type"]), uuid.UUID(data["workspace_id"]), uuid.UUID(data["target_id"])
        )


@dataclass(frozen=True, slots=True)
class ReceivedJob:
    job: Job
    receipt: str
    receive_count: int


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None: ...

    async def backlog(self) -> int: ...

    async def check(self) -> None: ...


Handler = Callable[[Job], Awaitable[object]]


class InlineQueue:
    """Runs jobs as background tasks in the API process. Development and tests."""

    def __init__(self) -> None:
        self._handler: Handler | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def bind(self, handler: Handler) -> None:
        self._handler = handler

    async def enqueue(self, job: Job) -> None:
        if self._handler is None:
            raise RuntimeError("InlineQueue has no handler bound")
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: Job) -> None:
        if self._handler is None:
            return
        try:
            await self._handler(job)
        except Exception:
            log.exception("inline_job_failed", job_type=job.type.value, target=str(job.target_id))

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def backlog(self) -> int:
        return len(self._tasks)

    async def check(self) -> None:
        return None


class SqsQueue:
    def __init__(self, settings: Settings) -> None:
        if not settings.sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL is required for QUEUE_BACKEND=sqs")
        self.url = settings.sqs_queue_url
        self._client = aws.sqs_client(settings)

    async def enqueue(self, job: Job) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.send_message(QueueUrl=self.url, MessageBody=job.encode())
        )

    async def receive(
        self, *, max_messages: int, wait_s: int, visibility_s: int
    ) -> list[ReceivedJob]:
        response = await anyio.to_thread.run_sync(
            lambda: self._client.receive_message(
                QueueUrl=self.url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_s,
                VisibilityTimeout=visibility_s,
                MessageSystemAttributeNames=["ApproximateReceiveCount"],
            )
        )
        received = []
        for message in response.get("Messages", []):
            try:
                job = Job.decode(message["Body"])
            except (ValueError, KeyError):
                log.warning("queue_message_malformed", message_id=message.get("MessageId"))
                await self.delete(message["ReceiptHandle"])
                continue
            count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            received.append(ReceivedJob(job, message["ReceiptHandle"], count))
        return received

    async def delete(self, receipt: str) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.delete_message(QueueUrl=self.url, ReceiptHandle=receipt)
        )

    async def extend(self, receipt: str, visibility_s: int) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.change_message_visibility(
                QueueUrl=self.url, ReceiptHandle=receipt, VisibilityTimeout=visibility_s
            )
        )

    async def backlog(self) -> int:
        """Messages waiting to be received (approximate, as SQS reports it)."""
        response = await anyio.to_thread.run_sync(
            lambda: self._client.get_queue_attributes(
                QueueUrl=self.url, AttributeNames=["ApproximateNumberOfMessages"]
            )
        )
        return int(response.get("Attributes", {}).get("ApproximateNumberOfMessages", "0"))

    async def check(self) -> None:
        await self.backlog()


def build_queue(settings: Settings) -> InlineQueue | SqsQueue:
    if settings.queue_backend == "sqs":
        return SqsQueue(settings)
    return InlineQueue()
