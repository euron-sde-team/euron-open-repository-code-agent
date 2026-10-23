"""The Docker sandbox: one throwaway container per run, through the Docker Engine API.

The container has networking disabled, every capability dropped, `no-new-privileges`, a
non-root user, and cgroup limits on memory (swap included), CPU and processes. The tree is
copied in as a tar stream (no bind mounts, so the run cannot touch the worker's disk),
the run is killed at its deadline, and the container is removed afterwards. Every
container is labelled, so leftovers from a crashed worker are removed at start-up.

The Engine API is spoken directly over the Unix socket with httpx: a few calls, fully
typed here, instead of a client library.
"""

from __future__ import annotations

import io
import secrets
import struct
import tarfile
import time
from pathlib import Path
from typing import Any

import anyio
import httpx

from codeagent.core import metrics
from codeagent.core.logging import get_logger
from codeagent.sandbox.types import LogBuffer, SandboxResult, SandboxSpec

log = get_logger("codeagent.sandbox.docker")
LABEL = "codeagent.run"
WORKDIR = "/workspace"
SANDBOX_USER = "10001:10001"


def tar_tree(root: Path) -> bytes:
    """The tree as a tar stream owned by the sandbox user; links are not followed."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:

        def owned(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
            if info.issym() or info.islnk() or not (info.isfile() or info.isdir()):
                return None
            info.uid = info.gid = 10001
            info.uname = info.gname = "sandbox"
            return info

        for entry in sorted(root.iterdir()):
            tar.add(entry, arcname=entry.name, filter=owned)
        marker = tarfile.TarInfo(".codeagent")
        marker.type = tarfile.DIRTYPE
        marker.mode = 0o755
        marker.uid = marker.gid = 10001
        tar.addfile(marker)
    return buffer.getvalue()


def demux(stream: bytes) -> bytes:
    """Docker multiplexes stdout and stderr in 8-byte-headed frames when there is no TTY."""
    out = bytearray()
    offset = 0
    while offset + 8 <= len(stream):
        size = struct.unpack(">I", stream[offset + 4 : offset + 8])[0]
        out += stream[offset + 8 : offset + 8 + size]
        offset += 8 + size
    return bytes(out)


def _file_from_tar(data: bytes) -> bytes | None:
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for member in tar:
                if member.isfile():
                    handle = tar.extractfile(member)
                    return handle.read() if handle is not None else None
    except tarfile.TarError:
        return None
    return None


class DockerSandbox:
    name = "docker"

    def __init__(self, socket_path: str, *, log_limit: int) -> None:
        self.socket_path = socket_path
        self.log_limit = log_limit
        self._client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=socket_path),
            base_url="http://docker",
            timeout=httpx.Timeout(30.0, connect=5.0),
        )

    async def available(self) -> bool:
        if not await anyio.Path(self.socket_path).exists():
            return False
        try:
            response = await self._client.get("/_ping", timeout=3.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def image_present(self, image: str) -> bool:
        response = await self._client.get(f"/images/{image}/json")
        return response.status_code == 200

    def _container(self, spec: SandboxSpec) -> dict[str, Any]:
        limits = spec.limits
        memory = limits.memory_mb * 1024 * 1024
        env = {
            "HOME": "/tmp",
            "TMPDIR": "/tmp",
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONHASHSEED": "0",
            "CODEAGENT_SANDBOX": "docker",
            **spec.env,
        }
        return {
            "Image": spec.image,
            "Cmd": ["/bin/sh", "-c", spec.command],
            "WorkingDir": WORKDIR,
            "User": SANDBOX_USER,
            "Env": [f"{key}={value}" for key, value in env.items()],
            "NetworkDisabled": True,
            "Labels": {LABEL: spec.label or "adhoc"},
            "HostConfig": {
                "NetworkMode": "none",
                "Memory": memory,
                "MemorySwap": memory,
                "NanoCpus": int(limits.cpus * 1_000_000_000),
                "PidsLimit": limits.pids,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Tmpfs": {"/tmp": "rw,nosuid,size=256m"},
                "Ulimits": [{"Name": "nofile", "Soft": 1024, "Hard": 1024}],
                "AutoRemove": False,
            },
        }

    async def run(self, spec: SandboxSpec) -> SandboxResult:
        started = time.perf_counter()
        archive = await anyio.to_thread.run_sync(tar_tree, spec.workdir)
        name = f"codeagent-run-{secrets.token_hex(6)}"
        created = await self._client.post(
            "/containers/create", params={"name": name}, json=self._container(spec)
        )
        if created.status_code == 404:
            return SandboxResult(
                backend=self.name,
                exit_code=None,
                image=spec.image,
                error=(
                    f"The sandbox image {spec.image} is not available on this Docker engine. "
                    "Build it with `make sandbox-image`."
                ),
            )
        created.raise_for_status()
        container = created.json()["Id"]
        timed_out = False
        try:
            put = await self._client.put(
                f"/containers/{container}/archive",
                params={"path": WORKDIR},
                content=archive,
                headers={"content-type": "application/x-tar"},
            )
            put.raise_for_status()
            (await self._client.post(f"/containers/{container}/start")).raise_for_status()
            try:
                waited = await self._client.post(
                    f"/containers/{container}/wait", timeout=spec.limits.timeout_s + 5
                )
                exit_code: int | None = int(waited.json().get("StatusCode", -1))
            except httpx.TimeoutException:
                timed_out = True
                exit_code = None
                await self._client.post(f"/containers/{container}/kill")
                await self._client.post(f"/containers/{container}/wait", timeout=30)
            state = (
                (await self._client.get(f"/containers/{container}/json")).json().get("State", {})
            )
            logs = await self._client.get(
                f"/containers/{container}/logs", params={"stdout": "1", "stderr": "1"}
            )
            buffer = LogBuffer(self.log_limit)
            buffer.write(demux(logs.content))
            outputs: dict[str, bytes] = {}
            for output in spec.outputs:
                fetched = await self._client.get(
                    f"/containers/{container}/archive", params={"path": f"{WORKDIR}/{output}"}
                )
                content = _file_from_tar(fetched.content) if fetched.status_code == 200 else None
                if content is not None:
                    outputs[output] = content
        finally:
            try:
                await self._client.delete(
                    f"/containers/{container}", params={"force": "1", "v": "1"}
                )
            except httpx.HTTPError:
                log.warning("sandbox_container_not_removed", container=container[:12])
        duration = time.perf_counter() - started
        oom = bool(state.get("OOMKilled"))
        outcome = "timed_out" if timed_out else ("passed" if exit_code == 0 else "failed")
        metrics.SANDBOX_RUNS.labels(self.name, outcome).inc()
        metrics.SANDBOX_DURATION.labels(self.name).observe(duration)
        return SandboxResult(
            backend=self.name,
            exit_code=exit_code,
            timed_out=timed_out,
            oom_killed=oom,
            duration_ms=int(duration * 1000),
            log=buffer.text(),
            log_truncated=buffer.truncated,
            outputs=outputs,
            image=spec.image,
        )

    async def remove_leftovers(self, older_than_s: int) -> int:
        """Containers a crashed worker left behind: labelled ones older than any live run."""
        response = await self._client.get(
            "/containers/json", params={"all": "1", "filters": f'{{"label":["{LABEL}"]}}'}
        )
        if response.status_code != 200:
            return 0
        cutoff = time.time() - older_than_s
        removed = 0
        for item in response.json():
            if int(item.get("Created", 0)) < cutoff:
                await self._client.delete(
                    f"/containers/{item['Id']}", params={"force": "1", "v": "1"}
                )
                removed += 1
        return removed

    async def aclose(self) -> None:
        await self._client.aclose()
