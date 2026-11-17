"""Probes, metrics and public deployment info."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from codeagent import __version__
from codeagent.agent.catalog import names as helper_names
from codeagent.api.deps import ContainerDep, SessionDep
from codeagent.core.logging import get_logger
from codeagent.repositories.users import UserRepository
from codeagent.schemas.system import EngineInfo, SandboxInfo, SystemInfo

router = APIRouter()
v1 = APIRouter(tags=["system"])
log = get_logger("codeagent.health")
SKILLS = ["rename", "fix_test", "add_function"]


@router.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(container: ContainerDep) -> JSONResponse:
    checks: dict[str, Any] = {}
    for name, probe in (
        ("database", container.db.ping),
        ("redis", container.redis.ping),
        ("queue", container.queue.check),
    ):
        try:
            await probe()
            checks[name] = "ok"
        except Exception as exc:
            log.warning("readiness_check_failed", check=name, error=type(exc).__name__)
            checks[name] = "failing"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@v1.get("/system/info", summary="Deployment capabilities and limits")
async def system_info(container: ContainerDep, session: SessionDep) -> SystemInfo:
    settings = container.settings
    chat = container.chat_client
    model_engine = EngineInfo(
        label=settings.model_label,
        provider=chat.provider if chat else "local",
        model=chat.model if chat else None,
        uses_model=chat is not None,
    )
    backend = container.sandbox_backend or (
        "docker" if settings.sandbox_backend == "docker" else settings.sandbox_backend
    )
    return SystemInfo(
        product_name=settings.product_name,
        version=__version__,
        answerer=model_engine,
        planner=model_engine,
        skills=SKILLS,
        helpers=helper_names(),
        embeddings=container.base_embedder.name,
        embedding_dim=settings.embedding_dim,
        sandbox=SandboxInfo(
            backend=backend,
            image=settings.sandbox_image if backend != "subprocess" else None,
            timeout_s=settings.sandbox_timeout_s,
            memory_mb=settings.sandbox_memory_mb,
            cpus=settings.sandbox_cpus,
            network="none",
        ),
        max_archive_mb=settings.max_archive_mb,
        allow_signup=settings.allow_signup,
        needs_setup=await UserRepository(session).count() == 0,
    )
