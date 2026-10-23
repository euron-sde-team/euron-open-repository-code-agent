"""Sandboxed command runs: Docker containers where a daemon is available, a limited
subprocess otherwise. `build_sandbox` picks the backend from SANDBOX_BACKEND."""

from __future__ import annotations

from codeagent.core.config import Settings
from codeagent.core.logging import get_logger
from codeagent.sandbox.docker import DockerSandbox
from codeagent.sandbox.process import SubprocessSandbox
from codeagent.sandbox.types import Limits, Sandbox, SandboxResult, SandboxSpec

__all__ = ["Limits", "Sandbox", "SandboxResult", "SandboxSpec", "build_sandbox", "default_limits"]

log = get_logger("codeagent.sandbox")


def default_limits(settings: Settings) -> Limits:
    return Limits(
        timeout_s=settings.sandbox_timeout_s,
        memory_mb=settings.sandbox_memory_mb,
        cpus=settings.sandbox_cpus,
        pids=settings.sandbox_pids,
    )


async def build_sandbox(settings: Settings) -> Sandbox:
    log_limit = settings.sandbox_log_kb * 1024
    if settings.sandbox_backend in {"auto", "docker"}:
        docker = DockerSandbox(settings.sandbox_docker_socket, log_limit=log_limit)
        if await docker.available():
            removed = await docker.remove_leftovers(settings.job_timeout_s)
            log.info(
                "sandbox_backend", backend="docker", image=settings.sandbox_image, removed=removed
            )
            return docker
        if settings.sandbox_backend == "docker":
            # Explicitly requested: keep it, so every run reports the missing daemon clearly.
            log.warning("sandbox_docker_unreachable", socket=settings.sandbox_docker_socket)
            return docker
        await docker.aclose()
    log.info("sandbox_backend", backend="subprocess", python=settings.sandbox_python)
    return SubprocessSandbox(settings.sandbox_python, log_limit=log_limit)
