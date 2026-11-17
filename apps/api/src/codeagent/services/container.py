"""Process-wide infrastructure, built once at startup and shared by every request and job.

Services are cheap objects created per request around one database session; everything
expensive (connection pools, HTTP clients, the sandbox client) lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from redis.asyncio import Redis

from codeagent.agent.planners import LocalPlanner, ModelPlanner
from codeagent.agent.types import Planner
from codeagent.ai.answerer import Answerer, LocalAnswerer, ModelAnswerer
from codeagent.ai.chat import ChatClient, build_chat_client
from codeagent.ai.embeddings import CachedEmbedder, Embedder, build_embedder
from codeagent.core.config import Settings
from codeagent.core.ratelimit import RateLimiter
from codeagent.db.session import Database
from codeagent.integrations.queue import InlineQueue, SqsQueue, build_queue
from codeagent.integrations.storage import Storage, build_storage
from codeagent.sandbox import Sandbox, build_sandbox


@dataclass
class Container:
    settings: Settings
    db: Database
    redis: Redis
    storage: Storage
    queue: InlineQueue | SqsQueue
    embedder: Embedder
    base_embedder: Embedder
    chat_client: ChatClient | None
    answerer: Answerer
    local_answerer: LocalAnswerer
    planner: Planner
    local_planner: LocalPlanner
    limiter: RateLimiter
    _sandbox: Sandbox | None = field(default=None, repr=False)

    async def sandbox(self) -> Sandbox:
        """The sandbox backend, chosen on first use (only processes that run tests need it)."""
        if self._sandbox is None:
            self._sandbox = await build_sandbox(self.settings)
        return self._sandbox

    @property
    def sandbox_backend(self) -> str | None:
        return self._sandbox.name if self._sandbox is not None else None

    async def close(self) -> None:
        if self._sandbox is not None:
            await self._sandbox.aclose()
        if self.chat_client is not None:
            await self.chat_client.aclose()
        closer = getattr(self.base_embedder, "aclose", None)
        if closer is not None:
            await closer()
        await self.redis.aclose()
        await self.db.dispose()


def build_container(settings: Settings) -> Container:
    redis = Redis.from_url(
        settings.redis_url, decode_responses=False, health_check_interval=30, socket_timeout=5
    )
    base_embedder = build_embedder(settings)
    chat_client = build_chat_client(settings)
    local_answerer = LocalAnswerer()
    local_planner = LocalPlanner(settings.agent_max_candidates)
    answerer: Answerer = ModelAnswerer(chat_client) if chat_client else local_answerer
    planner: Planner = (
        ModelPlanner(
            chat_client,
            max_iterations=settings.agent_max_iterations,
            context_tokens=settings.agent_context_tokens,
        )
        if chat_client
        else local_planner
    )
    return Container(
        settings=settings,
        db=Database(settings),
        redis=redis,
        storage=build_storage(settings),
        queue=build_queue(settings),
        embedder=CachedEmbedder(base_embedder, redis, settings.embedding_cache_ttl_s),
        base_embedder=base_embedder,
        chat_client=chat_client,
        answerer=answerer,
        local_answerer=local_answerer,
        planner=planner,
        local_planner=local_planner,
        limiter=RateLimiter(redis),
    )
