"""Integration fixtures: real Postgres (pgvector), Valkey and the Floci AWS emulator.

`make test-integration` starts all three (scripts/test-deps.sh, ports 5459, 6419 and 4619)
and runs this suite. It works in a database of its own (`codeagent_test`, recreated on
every run), Valkey database 15 (flushed on every run), and a KMS key, bucket and SQS queues
created for the run on the emulator, so nothing else is touched. Point it elsewhere with
TEST_DATABASE_ADMIN_URL, TEST_REDIS_URL and TEST_AWS_ENDPOINT_URL.

Tests run the real application over ASGI with the inline job queue, so an upload is
indexed, a task is planned and a test run is executed for real, in the same process.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import asyncpg
import boto3
import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.engine import URL, make_url

from codeagent.core.config import Settings, get_settings
from codeagent.db.migrate import migrate
from codeagent.main import create_app
from tests.integration.support import Member, Workspace, new_workspace

# The emulator accepts any credentials; real ones must never be sent to it.
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
for _name in ("AWS_SESSION_TOKEN", "AWS_PROFILE"):
    os.environ.pop(_name, None)

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL", "postgresql://codeagent:codeagent@localhost:5459/codeagent"
)
REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6419/15")
AWS_ENDPOINT = os.environ.get("TEST_AWS_ENDPOINT_URL", "http://localhost:4619")
TEST_DATABASE = os.environ.get("TEST_DATABASE_NAME", "codeagent_test")
WEB_ORIGIN = "http://localhost:3190"
RUN = uuid.uuid4().hex[:8]


def database_url(name: str) -> str:
    admin = make_url(ADMIN_URL)
    return URL.create(
        "postgresql+asyncpg",
        username=admin.username,
        password=admin.password,
        host=admin.host,
        port=admin.port,
        database=name,
    ).render_as_string(hide_password=False)


async def recreate_database(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def aws_client(service: str) -> Any:
    return boto3.client(service, endpoint_url=AWS_ENDPOINT, region_name="us-east-1")


@dataclass(frozen=True)
class AwsResources:
    kms_key_id: str
    bucket: str
    queue_url: str
    dlq_url: str


def provision_aws() -> AwsResources:
    """A KMS key, a bucket and the jobs queue with its dead-letter queue, like Terraform."""
    key_id = aws_client("kms").create_key(Description=f"codeagent integration {RUN}")[
        "KeyMetadata"
    ]["KeyId"]
    bucket = f"codeagent-it-{RUN}"
    aws_client("s3").create_bucket(Bucket=bucket)
    sqs = aws_client("sqs")
    dlq_url = sqs.create_queue(QueueName=f"codeagent-it-{RUN}-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    queue_url = sqs.create_queue(
        QueueName=f"codeagent-it-{RUN}",
        Attributes={
            "VisibilityTimeout": "30",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}),
        },
    )["QueueUrl"]
    return AwsResources(key_id, bucket, queue_url, dlq_url)


def make_settings(aws: AwsResources, **overrides: Any) -> Settings:
    """Test settings, independent of the developer's environment variables."""
    values: dict[str, Any] = {
        "app_env": "test",
        "log_level": "warning",
        "database_url": database_url(TEST_DATABASE),
        "redis_url": REDIS_URL,
        "session_secret": "integration-session-secret-0123456789abcdef",
        "api_key_pepper": "integration-api-key-pepper-0123456789abcdef",
        "cors_origins": [WEB_ORIGIN],
        "web_url": WEB_ORIGIN,
        "allow_signup": True,
        "aws_endpoint_url": AWS_ENDPOINT,
        "aws_region": "us-east-1",
        "storage_backend": "s3",
        "s3_bucket": aws.bucket,
        "s3_kms_key_id": aws.kms_key_id,
        "queue_backend": "inline",
        "sqs_queue_url": aws.queue_url,
        "sandbox_backend": "subprocess",
        "sandbox_python": sys.executable,
        "sandbox_timeout_s": 120,
        "job_timeout_s": 300,
        "embeddings_provider": "local",
        "llm_provider": "none",
        "rate_limit_ask": 100_000,
        "rate_limit_login": 100_000,
        "rate_limit_tasks": 100_000,
        "rate_limit_runs": 100_000,
        "rate_limit_upload": 100_000,
        "rate_limit_search": 100_000,
        "stale_job_minutes": 1,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture(scope="session")
def aws() -> AwsResources:
    return provision_aws()


@pytest.fixture(scope="session")
async def settings(aws: AwsResources) -> Settings:
    get_settings.cache_clear()
    settings = make_settings(aws)
    await recreate_database(TEST_DATABASE)
    await migrate(settings)
    redis = Redis.from_url(REDIS_URL)
    await redis.flushdb()
    await redis.aclose()
    return settings


@pytest.fixture(scope="session")
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """The real application over ASGI: real database, cache, S3 and in-process jobs."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.test", timeout=120
        ) as http:
            yield http


@pytest.fixture(scope="session")
def container(client: httpx.AsyncClient) -> Any:
    transport = client._transport
    assert isinstance(transport, httpx.ASGITransport)
    return transport.app.state.container  # type: ignore[attr-defined]


@pytest.fixture
async def workspace(client: httpx.AsyncClient) -> Workspace:
    """A fresh workspace with an owner, and a member of every other role."""
    return await new_workspace(client)


@pytest.fixture
async def stranger(client: httpx.AsyncClient) -> Member:
    """Somebody with an account and a workspace of their own, and no access to anyone else's."""
    return (await new_workspace(client, members=False)).owner
