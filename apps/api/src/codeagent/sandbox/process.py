"""The subprocess sandbox: for hosts without a Docker daemon (Fargate, CI runners).

Each run gets the worker's unprivileged user, a new session (so a timeout kills the whole
process group), POSIX resource limits on CPU time, address space, processes, open files
and file size, no core dumps, an environment scrubbed down to what a test runner needs,
proxies that point at a closed port, and a `sitecustomize` network guard for Python.
It is weaker than the Docker backend, which has a separate network namespace and cgroup
limits; docs/architecture/security.md explains where each is used.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import resource
import shlex
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path

from codeagent.core import metrics
from codeagent.sandbox.types import Limits, LogBuffer, SandboxResult, SandboxSpec

GUARD_DIR = Path(__file__).resolve().parent / "guard"
_CLOSED_PROXY = "http://127.0.0.1:9"  # the discard port: nothing listens there


def _limiter(limits: Limits) -> Callable[[], None]:
    memory = limits.memory_mb * 1024 * 1024
    cpu_seconds = max(1, int(limits.timeout_s * max(limits.cpus, 1)))

    def apply() -> None:
        os.setsid()
        settings: list[tuple[int, int]] = [
            (resource.RLIMIT_CPU, cpu_seconds),
            (resource.RLIMIT_FSIZE, 256 * 1024 * 1024),
            (resource.RLIMIT_NOFILE, 1024),
            (resource.RLIMIT_CORE, 0),
        ]
        # Address-space and per-user process limits are enforced reliably on Linux only;
        # on macOS RLIMIT_NPROC counts every process of the developer's account.
        if sys.platform.startswith("linux"):
            settings += [(resource.RLIMIT_AS, memory), (resource.RLIMIT_NPROC, limits.pids)]
        for which, value in settings:
            try:
                _soft, hard = resource.getrlimit(which)
                cap = value if hard == resource.RLIM_INFINITY else min(value, hard)
                resource.setrlimit(which, (cap, cap))
            except (ValueError, OSError):
                continue

    return apply


class SubprocessSandbox:
    name = "subprocess"

    def __init__(self, python: str, *, log_limit: int) -> None:
        self.python = python
        self.log_limit = log_limit

    def _environment(self, spec: SandboxSpec, home: Path) -> dict[str, str]:
        interpreter_dir = os.path.dirname(self.python) if os.path.sep in self.python else ""
        # The interpreter's own directory comes first, so `python` and the tools installed
        # next to it (pytest) resolve to the sandbox environment.
        path = ":".join(p for p in (interpreter_dir, "/usr/local/bin", "/usr/bin", "/bin") if p)
        env = {
            "PATH": path,
            "HOME": str(home),
            "TMPDIR": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(GUARD_DIR),
            "CODEAGENT_SANDBOX": "subprocess",
            "http_proxy": _CLOSED_PROXY,
            "https_proxy": _CLOSED_PROXY,
            "all_proxy": _CLOSED_PROXY,
            "HTTP_PROXY": _CLOSED_PROXY,
            "HTTPS_PROXY": _CLOSED_PROXY,
            "ALL_PROXY": _CLOSED_PROXY,
            "no_proxy": "",
        }
        env.update(spec.env)
        return env

    async def run(self, spec: SandboxSpec) -> SandboxResult:
        started = time.perf_counter()
        home = spec.workdir / ".codeagent" / "home"
        home.mkdir(parents=True, exist_ok=True)
        for output in spec.outputs:
            (spec.workdir / output).parent.mkdir(parents=True, exist_ok=True)
        command = spec.command
        if command.startswith("python "):
            command = f"{shlex.quote(self.python)} {command.removeprefix('python ')}"
        process = await asyncio.create_subprocess_exec(
            "/bin/sh",
            "-c",
            command,
            cwd=spec.workdir,
            env=self._environment(spec, home),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            # The limits must be set in the child between fork and exec; preexec_fn is the
            # only hook for that, and the child runs no Python threads before exec.
            preexec_fn=_limiter(spec.limits),
        )
        buffer = LogBuffer(self.log_limit)

        async def pump() -> None:
            if process.stdout is None:
                return
            while chunk := await process.stdout.read(65536):
                buffer.write(chunk)

        timed_out = False
        reader = asyncio.create_task(pump())
        try:
            await asyncio.wait_for(process.wait(), spec.limits.timeout_s)
        except TimeoutError:
            timed_out = True
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        try:
            await asyncio.wait_for(reader, 5)
        except TimeoutError:
            reader.cancel()
        outputs = {}
        for output in spec.outputs:
            target = spec.workdir / output
            if target.is_file() and not target.is_symlink():
                outputs[output] = target.read_bytes()[: 8 * 1024 * 1024]
        duration = time.perf_counter() - started
        outcome = "timed_out" if timed_out else ("passed" if process.returncode == 0 else "failed")
        metrics.SANDBOX_RUNS.labels(self.name, outcome).inc()
        metrics.SANDBOX_DURATION.labels(self.name).observe(duration)
        return SandboxResult(
            backend=self.name,
            exit_code=None if timed_out else process.returncode,
            timed_out=timed_out,
            duration_ms=int(duration * 1000),
            log=buffer.text(),
            log_truncated=buffer.truncated,
            outputs=outputs,
            image=None,
        )

    async def aclose(self) -> None:
        return None
