"""The FastAPI application factory.

uvicorn codeagent.main:create_app --factory --port 8190
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codeagent import __version__
from codeagent.api.router import api_router
from codeagent.core.config import Settings, get_settings
from codeagent.core.context import BodySizeLimitMiddleware, RequestContextMiddleware
from codeagent.core.errors import install_exception_handlers
from codeagent.core.logging import configure_logging, get_logger
from codeagent.db.migrate import migrate
from codeagent.integrations.queue import InlineQueue
from codeagent.services.container import build_container
from codeagent.services.jobs import JobDispatcher

log = get_logger("codeagent.app")

DESCRIPTION = """
A repository-aware coding assistant: a code index with symbol, text and semantic search,
answers that cite files and lines, sandboxed test runs, and patch proposals that a person
reviews before anything is applied.

Authenticate with `Authorization: Bearer <key>` using a workspace API key (`cak_...`), or
with the web app's session cookie. Every error uses one envelope:
`{"error": {"code", "message", "request_id", "details?"}}`, and every response carries
`X-Request-Id`.
"""

TAGS = [
    {"name": "repositories", "description": "Connect, index and browse code."},
    {"name": "search", "description": "Symbol, text and semantic search."},
    {"name": "ask", "description": "Conversations and answers with citations."},
    {"name": "tasks", "description": "Describe a change for the agent."},
    {"name": "review", "description": "Diffs, comments, approval, apply and export."},
    {"name": "test runs", "description": "Sandboxed test runs, results and logs."},
    {"name": "workspaces", "description": "Workspaces, members, API keys, audit and overview."},
    {"name": "auth", "description": "Sign-in, sessions and the caller's identity."},
    {"name": "system", "description": "Deployment capabilities and limits."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.is_production and (problems := settings.production_problems()):
        raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(problems))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_boot:
            await migrate(settings)
        container = build_container(settings)
        if isinstance(container.queue, InlineQueue):
            container.queue.bind(JobDispatcher(container).handle)
        app.state.container = container
        log.info(
            "started",
            version=__version__,
            env=settings.app_env,
            answerer=container.answerer.label,
            embeddings=container.base_embedder.name,
            queue=settings.queue_backend,
            storage=settings.storage_backend,
        )
        try:
            yield
        finally:
            if isinstance(container.queue, InlineQueue):
                await container.queue.drain()
            await container.close()

    app = FastAPI(
        title=settings.product_name,
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
        license_info={"name": "MIT", "identifier": "MIT"},
    )
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-request-id"],
        expose_headers=[
            "x-request-id",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset",
            "content-disposition",
        ],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
    app.include_router(api_router)
    return app
