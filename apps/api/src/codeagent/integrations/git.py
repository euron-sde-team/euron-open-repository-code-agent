"""Git, run as a subprocess with a locked-down configuration.

Repositories handled here are untrusted, so every invocation:

- ignores system and global configuration and never prompts for credentials;
- disables hooks and fsmonitor (the two ways a repository can make git run a program);
- for anything that talks to a remote, allows only HTTPS and refuses redirects, so a URL
  cannot be bounced to an internal address after it was checked;
- runs with a timeout, a fixed locale and a scrubbed environment.

Only the worker calls this module. The API never touches a working tree.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import anyio

from codeagent.core.errors import UnprocessableError

BOT_NAME = "Euron CodeAgent"
BOT_EMAIL = "codeagent@localhost"

_SAFE_CONFIG = (
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "core.autocrlf=false",
    "-c", "core.quotePath=false",
    "-c", "advice.detachedHead=false",
    "-c", "init.defaultBranch=main",
    "-c", "commit.gpgSign=false",
    "-c", "tag.gpgSign=false",
    "-c", "safe.directory=*",
)  # fmt: skip
_REMOTE_CONFIG = (
    "-c", "protocol.allow=never",
    "-c", "protocol.https.allow=always",
    "-c", "http.followRedirects=false",
    "-c", "credential.helper=",
    "-c", "submodule.recurse=false",
)  # fmt: skip
_URL = re.compile(r"^https://[A-Za-z0-9.-]+(?::\d{1,5})?/[A-Za-z0-9._~%+/-]+$")
_BRANCH = re.compile(r"^(?!.*\.\.)(?!/)(?!.*//)[A-Za-z0-9._/-]{1,200}(?<![./])$")


class GitError(Exception):
    """A git command failed. `detail` is the tail of its stderr, for logs and job errors."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail[-2000:]


@dataclass(frozen=True, slots=True)
class Head:
    sha: str
    branch: str


def validate_git_url(url: str) -> str:
    """An HTTPS clone URL without credentials, or a 422 explaining what is wrong."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnprocessableError("Use an HTTPS clone URL (https://host/owner/repo.git).")
    if parts.username or parts.password:
        raise UnprocessableError(
            "Do not put credentials in the URL. Public repositories need none.",
            code="credentials_in_url",
        )
    if not _URL.match(url) or parts.query or parts.fragment:
        raise UnprocessableError("That does not look like a git clone URL.", code="invalid_git_url")
    return url


def validate_branch(branch: str) -> str:
    branch = branch.strip()
    if not _BRANCH.match(branch) or branch.startswith("-"):
        raise UnprocessableError("That is not a valid branch name.", code="invalid_branch")
    return branch


async def ensure_public_host(url: str, *, allow_private: bool) -> None:
    """Refuse hosts that resolve to loopback, private, link-local or reserved addresses.

    Git resolves the name again when it connects; redirects are disabled, so the remaining
    window is DNS rebinding between the two lookups, which the threat model accepts.
    """
    host = urlsplit(url).hostname or ""
    if allow_private:
        return
    if host in {"localhost"} or host.endswith((".localhost", ".internal", ".local")):
        raise UnprocessableError("That host is not reachable from CodeAgent.", code="private_host")
    try:
        infos = await anyio.to_thread.run_sync(
            lambda: socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        )
    except OSError as exc:
        raise UnprocessableError(f"Could not resolve {host}.", code="unresolvable_host") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UnprocessableError(
                "That host resolves to a private address, which CodeAgent does not clone from.",
                code="private_host",
            )


def _environment(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": BOT_NAME,
        "GIT_AUTHOR_EMAIL": BOT_EMAIL,
        "GIT_COMMITTER_NAME": BOT_NAME,
        "GIT_COMMITTER_EMAIL": BOT_EMAIL,
    }


async def git(
    *args: str,
    cwd: Path,
    timeout_s: float = 120,
    remote: bool = False,
    stdin: bytes | None = None,
) -> str:
    """Run one git command and return its stdout. Raises GitError with stderr on failure."""
    command = ("git", *_SAFE_CONFIG, *(_REMOTE_CONFIG if remote else ()), *args)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=_environment(cwd),
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(stdin), timeout_s)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise GitError(f"git {args[0]} took longer than {int(timeout_s)} seconds") from exc
    if process.returncode != 0:
        raise GitError(f"git {args[0]} failed", err.decode("utf-8", "replace"))
    return out.decode("utf-8", "replace")


async def clone(url: str, dest: Path, *, branch: str | None, depth: int, timeout_s: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--quiet", "--no-tags", "--single-branch", f"--depth={depth}"]
    if branch:
        args += ["--branch", branch]
    try:
        await git(*args, "--", url, str(dest), cwd=dest.parent, timeout_s=timeout_s, remote=True)
    except GitError as exc:
        raise GitError(
            "Cloning the repository failed. Check the URL and branch.", exc.detail
        ) from exc


async def fetch_and_reset(repo: Path, *, branch: str, depth: int, timeout_s: float) -> None:
    """Move the working tree to the remote's latest commit on `branch`."""
    await git(
        "fetch", "--quiet", "--no-tags", f"--depth={depth}", "origin", branch,
        cwd=repo, timeout_s=timeout_s, remote=True,
    )  # fmt: skip
    await git("checkout", "--quiet", "-B", branch, "FETCH_HEAD", cwd=repo)
    await git("reset", "--quiet", "--hard", "FETCH_HEAD", cwd=repo)
    await git("clean", "-fdqx", cwd=repo)


async def remote_url(repo: Path) -> str | None:
    try:
        return (await git("config", "--get", "remote.origin.url", cwd=repo)).strip() or None
    except GitError:
        return None


async def commit_tree(repo: Path, message: str) -> str:
    """Commit everything in the working tree (creating the repository if needed)."""
    if not (repo / ".git").exists():
        await git("init", "--quiet", "--initial-branch=main", cwd=repo)
    await git("add", "--all", cwd=repo)
    await git("commit", "--quiet", "--allow-empty", "--no-verify", "-m", message, cwd=repo)
    return (await head(repo)).sha


async def head(repo: Path) -> Head:
    sha = (await git("rev-parse", "HEAD", cwd=repo)).strip()
    branch = (await git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)).strip()
    return Head(sha, "HEAD" if branch == "HEAD" else branch)


async def tracked_files(repo: Path) -> list[str]:
    output = await git("ls-files", "-z", cwd=repo)
    return [path for path in output.split("\0") if path]


async def checkout(repo: Path, sha: str) -> None:
    await git("checkout", "--quiet", "--force", "--detach", sha, cwd=repo)
    await git("clean", "-fdqx", cwd=repo)


async def branch_exists(repo: Path, name: str) -> bool:
    try:
        await git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}", cwd=repo)
    except GitError:
        return False
    return True


async def apply_check(repo: Path, patch: str) -> None:
    try:
        await git("apply", "--check", "--whitespace=nowarn", "-", cwd=repo, stdin=patch.encode())
    except GitError as exc:
        raise GitError("The patch does not apply to the base commit.", exc.detail) from exc


async def apply(repo: Path, patch: str) -> None:
    try:
        await git(
            "apply", "--index", "--3way", "--whitespace=nowarn", "-",
            cwd=repo, stdin=patch.encode(),
        )  # fmt: skip
    except GitError as exc:
        raise GitError("The patch does not apply to the base commit.", exc.detail) from exc


async def commit_on_branch(repo: Path, *, branch: str, start: str, patch: str, message: str) -> str:
    """Create `branch` at `start`, apply `patch` and commit it. Returns the commit sha."""
    await git("checkout", "--quiet", "--force", "-B", branch, start, cwd=repo)
    await apply(repo, patch)
    await git("commit", "--quiet", "--no-verify", "-m", message, cwd=repo)
    return (await head(repo)).sha


def pack(source: Path, archive: Path) -> None:
    """The whole working tree, `.git` included, as a gzip tarball."""
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        for entry in sorted(source.iterdir()):
            tar.add(entry, arcname=entry.name)


def unpack(archive: Path, dest: Path) -> None:
    """Restore a mirror written by `pack`. The data filter still refuses unsafe members."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest, filter="data")


def scratch_dir(prefix: str) -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=f"codeagent-{prefix}-")
