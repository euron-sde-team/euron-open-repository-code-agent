"""The subprocess sandbox runs real processes: limits, scrubbed environment, no network."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from codeagent.sandbox import Limits
from codeagent.sandbox.junit import parse_junit, parse_pytest_summary
from codeagent.sandbox.process import SubprocessSandbox
from codeagent.sandbox.types import JUNIT_PATH, LogBuffer, SandboxSpec, prepare_command, strip_ansi

LIMITS = Limits(timeout_s=20, memory_mb=1024, cpus=1.0, pids=256)


@pytest.fixture
def sandbox() -> SubprocessSandbox:
    return SubprocessSandbox(sys.executable, log_limit=64 * 1024)


def spec(tmp_path: Path, command: str, **kwargs: object) -> SandboxSpec:
    return SandboxSpec(
        workdir=tmp_path,
        command=command,
        limits=kwargs.pop("limits", LIMITS),
        image="-",
        **kwargs,  # type: ignore[arg-type]
    )


async def test_a_command_runs_in_its_own_directory_and_reports_its_exit_code(
    sandbox: SubprocessSandbox, tmp_path: Path
) -> None:
    (tmp_path / "hello.txt").write_text("hi")
    ok = await sandbox.run(spec(tmp_path, "cat hello.txt && pwd"))
    assert ok.exit_code == 0
    assert "hi" in ok.log
    assert ok.backend == "subprocess"
    failed = await sandbox.run(spec(tmp_path, "exit 3"))
    assert failed.exit_code == 3
    assert failed.outcome == "failed"


async def test_a_run_past_its_deadline_is_killed(
    sandbox: SubprocessSandbox, tmp_path: Path
) -> None:
    limits = Limits(timeout_s=1, memory_mb=1024, cpus=1.0, pids=256)
    result = await sandbox.run(spec(tmp_path, "sleep 30", limits=limits))
    assert result.timed_out
    assert result.exit_code is None
    assert result.outcome == "timed_out"
    assert result.duration_ms < 10_000


async def test_the_environment_is_scrubbed(
    sandbox: SubprocessSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret-value")
    monkeypatch.setenv("SESSION_SECRET", "another-secret-value")
    result = await sandbox.run(spec(tmp_path, "env"))
    assert "super-secret-value" not in result.log
    assert "another-secret-value" not in result.log
    assert "CODEAGENT_SANDBOX=subprocess" in result.log
    assert os.environ["AWS_SECRET_ACCESS_KEY"] == "super-secret-value"


async def test_python_cannot_reach_the_network(sandbox: SubprocessSandbox, tmp_path: Path) -> None:
    script = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('93.184.216.34', 80), timeout=2)\n"
        "    print('CONNECTED')\n"
        "except OSError as exc:\n"
        "    print('BLOCKED', exc)\n"
    )
    (tmp_path / "probe.py").write_text(script)
    result = await sandbox.run(spec(tmp_path, "python probe.py"))
    assert "BLOCKED" in result.log
    assert "CONNECTED" not in result.log
    assert "disabled in the CodeAgent sandbox" in result.log


async def test_name_lookups_are_refused_too(sandbox: SubprocessSandbox, tmp_path: Path) -> None:
    (tmp_path / "dns.py").write_text(
        "import socket\n"
        "try:\n    socket.getaddrinfo('example.com', 443)\n    print('RESOLVED')\n"
        "except OSError:\n    print('REFUSED')\n"
    )
    result = await sandbox.run(spec(tmp_path, "python dns.py"))
    assert "REFUSED" in result.log


async def test_loopback_still_works_for_tests_that_start_a_local_server(
    sandbox: SubprocessSandbox, tmp_path: Path
) -> None:
    (tmp_path / "loop.py").write_text(
        "import socket\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen()\n"
        "c = socket.create_connection(s.getsockname(), timeout=2)\n"
        "print('LOOPBACK-OK')\n"
    )
    result = await sandbox.run(spec(tmp_path, "python loop.py"))
    assert "LOOPBACK-OK" in result.log


async def test_junit_output_is_brought_back(sandbox: SubprocessSandbox, tmp_path: Path) -> None:
    (tmp_path / "test_a.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n\ndef test_bad():\n    assert 1 == 2\n"
    )
    command = prepare_command("python -m pytest -q")
    result = await sandbox.run(spec(tmp_path, command))
    assert result.exit_code == 1
    assert result.junit_xml is not None
    summary = parse_junit(result.junit_xml)
    assert summary is not None
    assert (summary.total, summary.passed, summary.failed) == (2, 1, 1)
    failing = next(c for c in summary.cases if c.status == "failed")
    assert failing.name == "test_bad"
    assert "assert 1 == 2" in failing.message
    assert JUNIT_PATH in result.outputs


async def test_a_huge_log_is_capped(sandbox: SubprocessSandbox, tmp_path: Path) -> None:
    (tmp_path / "noisy.py").write_text("for i in range(200000):\n    print('x' * 50)\n")
    result = await sandbox.run(spec(tmp_path, "python noisy.py"))
    assert result.log_truncated
    assert len(result.log.encode()) <= 70 * 1024


def test_prepare_command_adds_junit_only_for_pytest() -> None:
    assert "--junitxml=" in prepare_command("python -m pytest -q")
    assert prepare_command("npm test") == "npm test"
    own = "pytest --junitxml=out.xml"
    assert prepare_command(own) == own


def test_log_buffer_keeps_the_head_and_marks_truncation() -> None:
    buffer = LogBuffer(100)
    buffer.write(b"a" * 80)
    buffer.write(b"b" * 80)
    assert buffer.truncated
    assert len(buffer.text().encode()) <= 200


def test_ansi_sequences_are_stripped() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m\r\nline") == "red\nline"


def test_the_pytest_summary_line_is_parsed_without_junit() -> None:
    summary = parse_pytest_summary("...\n=== 2 failed, 24 passed, 1 skipped in 0.31s ===\n")
    assert summary is not None
    assert (summary.total, summary.failed, summary.passed, summary.skipped) == (27, 2, 24, 1)
    assert parse_pytest_summary("no summary here") is None


def test_junit_with_malformed_or_hostile_xml_is_rejected() -> None:
    assert parse_junit(b"<testsuite><testcase") is None
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><testsuite><testcase name="&a;"/></testsuite>'
    assert parse_junit(bomb) is None
