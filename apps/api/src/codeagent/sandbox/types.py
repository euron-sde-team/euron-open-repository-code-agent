"""The sandbox contract: what a run needs and what it reports, for every backend."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

JUNIT_PATH = ".codeagent/junit.xml"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass(frozen=True, slots=True)
class Limits:
    timeout_s: int
    memory_mb: int
    cpus: float
    pids: int

    def public(self) -> dict[str, object]:
        return {
            "timeout_s": self.timeout_s,
            "memory_mb": self.memory_mb,
            "cpus": self.cpus,
            "pids": self.pids,
            "network": "none",
        }


@dataclass(slots=True)
class SandboxSpec:
    """Run `command` in `workdir`. The directory is the run's own copy and may be changed.

    `outputs` are files (relative to the working directory) to bring back after the run.
    """

    workdir: Path
    command: str
    limits: Limits
    image: str
    env: dict[str, str] = field(default_factory=dict)
    outputs: tuple[str, ...] = (JUNIT_PATH,)
    label: str = ""


@dataclass(slots=True)
class SandboxResult:
    backend: str
    exit_code: int | None
    timed_out: bool = False
    oom_killed: bool = False
    duration_ms: int = 0
    log: str = ""
    log_truncated: bool = False
    outputs: dict[str, bytes] = field(default_factory=dict)
    image: str | None = None
    error: str | None = None

    @property
    def junit_xml(self) -> bytes | None:
        return self.outputs.get(JUNIT_PATH)

    @property
    def outcome(self) -> str:
        if self.error:
            return "error"
        if self.timed_out:
            return "timed_out"
        return "passed" if self.exit_code == 0 else "failed"


class Sandbox(Protocol):
    name: str

    async def run(self, spec: SandboxSpec) -> SandboxResult: ...

    async def aclose(self) -> None: ...


class LogBuffer:
    """Keeps the head and the tail of a stream within a byte budget.

    Test logs put collection errors at the start and the failure summary at the end, so
    both ends are worth more than the middle.
    """

    def __init__(self, limit: int, head: int | None = None) -> None:
        self.limit = limit
        self.head_limit = head if head is not None else limit // 4
        self.head = bytearray()
        self.tail = bytearray()
        self.dropped = 0

    def write(self, data: bytes) -> None:
        if len(self.head) < self.head_limit:
            take = self.head_limit - len(self.head)
            self.head += data[:take]
            data = data[take:]
        if not data:
            return
        self.tail += data
        overflow = len(self.tail) - (self.limit - self.head_limit)
        if overflow > 0:
            del self.tail[:overflow]
            self.dropped += overflow

    def text(self) -> str:
        middle = f"\n... [{self.dropped} bytes of output omitted] ...\n" if self.dropped else ""
        raw = bytes(self.head).decode("utf-8", "replace") + middle
        raw += bytes(self.tail).decode("utf-8", "replace")
        return strip_ansi(raw)

    @property
    def truncated(self) -> bool:
        return self.dropped > 0


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text).replace("\r\n", "\n")


def prepare_command(command: str, junit_path: str = JUNIT_PATH) -> str:
    """Make pytest write JUnit XML (and no cache) unless the command already chose."""
    command = command.strip()
    if "pytest" in command and "--junitxml" not in command and "--junit-xml" not in command:
        command = f"{command} --junitxml={junit_path} -p no:cacheprovider"
    return command
