"""The Docker sandbox against a real engine (skipped where Docker is not reachable)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from codeagent.sandbox import Limits
from codeagent.sandbox.docker import DockerSandbox, demux
from codeagent.sandbox.types import SandboxSpec

pytestmark = pytest.mark.docker
IMAGE = "python:3.12-slim-bookworm"


def socket_path() -> str:
    host = os.environ.get("DOCKER_HOST", "")
    if host.startswith("unix://"):
        return host.removeprefix("unix://")
    colima = Path.home() / ".colima" / "default" / "docker.sock"
    return str(colima) if colima.exists() else "/var/run/docker.sock"


@pytest.fixture
async def docker() -> AsyncIterator[DockerSandbox]:
    sandbox = DockerSandbox(socket_path(), log_limit=64 * 1024)
    if not await sandbox.available():
        await sandbox.aclose()
        pytest.skip("no Docker engine is reachable")
    if not await sandbox.image_present(IMAGE):
        await sandbox.aclose()
        pytest.skip(f"{IMAGE} is not present locally")
    yield sandbox
    await sandbox.aclose()


def spec(tmp_path: Path, command: str, **limits: float) -> SandboxSpec:
    values = {"timeout_s": 30, "memory_mb": 256, "cpus": 1.0, "pids": 128, **limits}
    return SandboxSpec(
        workdir=tmp_path,
        command=command,
        limits=Limits(**values),  # type: ignore[arg-type]
        image=IMAGE,
        label="unit-test",
    )


async def test_a_command_runs_inside_a_container(docker: DockerSandbox, tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text("print('from the container')\n")
    result = await docker.run(spec(tmp_path, "python hello.py && id -u"))
    assert result.exit_code == 0, result.log
    assert "from the container" in result.log
    assert "10001" in result.log
    assert result.backend == "docker"


async def test_there_is_no_network(docker: DockerSandbox, tmp_path: Path) -> None:
    (tmp_path / "net.py").write_text(
        "import socket\n"
        "try:\n    socket.create_connection(('1.1.1.1', 80), timeout=3); print('CONNECTED')\n"
        "except OSError as exc:\n    print('NO NETWORK', exc)\n"
    )
    result = await docker.run(spec(tmp_path, "python net.py"))
    assert "NO NETWORK" in result.log
    assert "CONNECTED" not in result.log


async def test_the_host_filesystem_is_not_visible(docker: DockerSandbox, tmp_path: Path) -> None:
    marker = tmp_path / "workdir-only.txt"
    marker.write_text("x")
    result = await docker.run(spec(tmp_path, f"ls /Users /home 2>&1; ls {marker.name}"))
    assert "workdir-only.txt" in result.log
    assert "aashishjha" not in result.log


async def test_memory_is_capped_and_reported(docker: DockerSandbox, tmp_path: Path) -> None:
    (tmp_path / "hog.py").write_text(
        "blocks = []\nwhile True:\n    blocks.append(bytearray(32 * 1024 * 1024))\n"
    )
    result = await docker.run(spec(tmp_path, "python hog.py", memory_mb=96))
    assert result.exit_code != 0
    assert result.oom_killed


async def test_a_run_past_its_deadline_is_killed_and_the_container_removed(
    docker: DockerSandbox, tmp_path: Path
) -> None:
    result = await docker.run(spec(tmp_path, "sleep 60", timeout_s=2))
    assert result.timed_out
    assert await docker.remove_leftovers(0) == 0


async def test_the_working_tree_changes_stay_in_the_container(
    docker: DockerSandbox, tmp_path: Path
) -> None:
    (tmp_path / "keep.txt").write_text("original")
    await docker.run(spec(tmp_path, "echo changed > keep.txt; rm -f keep.txt"))
    assert (tmp_path / "keep.txt").read_text() == "original"


async def test_a_missing_image_is_a_clear_error(docker: DockerSandbox, tmp_path: Path) -> None:
    missing = spec(tmp_path, "true")
    missing.image = "codeagent-no-such-image:0"
    result = await docker.run(missing)
    assert result.error is not None
    assert "make sandbox-image" in result.error


def test_docker_log_frames_are_demultiplexed() -> None:
    frame = b"\x01\x00\x00\x00\x00\x00\x00\x05hello" + b"\x02\x00\x00\x00\x00\x00\x00\x03err"
    assert demux(frame) == b"helloerr"
