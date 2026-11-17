from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from codeagent.core.config import Settings
from codeagent.core.errors import NotFoundError, UnprocessableError
from codeagent.integrations import git
from codeagent.integrations.queue import InlineQueue, Job, JobType, build_queue
from codeagent.integrations.storage import (
    LocalStorage,
    build_storage,
    mirror_key,
    repository_prefix,
    upload_key,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/euron-sde-team/euron-open-repository-code-agent.git",
        "https://gitlab.com/group/sub/repo",
        "https://git.example.com:8443/team/repo.git",
    ],
)
def test_https_clone_urls_are_accepted(url: str) -> None:
    assert git.validate_git_url(url) == url


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://github.com/a/b.git", None),
        ("ssh://git@github.com/a/b.git", None),
        ("file:///etc/passwd", None),
        ("https://user:token@github.com/a/b.git", "credentials_in_url"),
        ("https://github.com/a/b.git?x=1", "invalid_git_url"),
        ("https://github.com/a/b.git#frag", "invalid_git_url"),
        ("https://github.com", "invalid_git_url"),
        ("https://exa mple.com/a/b", "invalid_git_url"),
    ],
)
def test_unsafe_clone_urls_are_refused(url: str, code: str | None) -> None:
    with pytest.raises(UnprocessableError) as caught:
        git.validate_git_url(url)
    if code:
        assert caught.value.code == code


@pytest.mark.parametrize("branch", ["main", "release/1.2", "feature_x-1"])
def test_branch_names_are_accepted(branch: str) -> None:
    assert git.validate_branch(branch) == branch


@pytest.mark.parametrize("branch", ["-delete", "a..b", "/abs", "x y", "a//b", "ends."])
def test_dangerous_branch_names_are_refused(branch: str) -> None:
    with pytest.raises(UnprocessableError):
        git.validate_branch(branch)


@pytest.mark.parametrize(
    "url", ["https://localhost/a/b", "https://db.internal/a/b", "https://printer.local/a/b"]
)
async def test_private_host_names_are_refused(url: str) -> None:
    with pytest.raises(UnprocessableError) as caught:
        await git.ensure_public_host(url, allow_private=False)
    assert caught.value.code == "private_host"


async def test_private_hosts_can_be_allowed_for_a_local_git_server() -> None:
    await git.ensure_public_host("https://localhost/a/b", allow_private=True)


async def test_literal_private_addresses_are_refused() -> None:
    for address in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1"):
        with pytest.raises(UnprocessableError):
            await git.ensure_public_host(f"https://{address}/a/b", allow_private=False)


async def test_git_runs_with_a_locked_down_configuration(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    await git.git("init", "-q", cwd=repo)
    (repo / "a.txt").write_text("one\n")
    sha = await git.commit_tree(repo, "Import a.txt")
    head = await git.head(repo)
    assert head.sha == sha
    assert await git.tracked_files(repo) == ["a.txt"]


async def test_a_patch_is_applied_on_a_new_branch_without_touching_the_base(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    await git.git("init", "-q", cwd=repo)
    (repo / "a.txt").write_text("one\n")
    base = await git.commit_tree(repo, "Import")
    patch = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-one\n+two\n"
    await git.apply_check(repo, patch)
    sha = await git.commit_on_branch(
        repo, branch="codeagent/1-change", start=base, patch=patch, message="Change a\n\nWhy.\n"
    )
    assert sha != base
    assert await git.branch_exists(repo, "codeagent/1-change")
    shown = await git.git("show", f"{sha}:a.txt", cwd=repo)
    assert shown.strip() == "two"
    base_file = await git.git("show", f"{base}:a.txt", cwd=repo)
    assert base_file.strip() == "one"


async def test_a_patch_that_does_not_apply_is_a_git_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    await git.git("init", "-q", cwd=repo)
    (repo / "a.txt").write_text("one\n")
    await git.commit_tree(repo, "Import")
    bad = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-nope\n+two\n"
    with pytest.raises(git.GitError):
        await git.apply_check(repo, bad)


def test_a_working_tree_survives_pack_and_unpack(tmp_path: Path) -> None:
    source = tmp_path / "src"
    (source / "d").mkdir(parents=True)
    (source / "d" / "f.txt").write_text("content")
    archive = tmp_path / "tree.tar.gz"
    git.pack(source, archive)
    target = tmp_path / "out"
    git.unpack(archive, target)
    assert (target / "d" / "f.txt").read_text() == "content"


async def test_local_storage_round_trips_and_rejects_unsafe_keys(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "files")
    await storage.put("workspaces/a/file.bin", b"data", "application/octet-stream")
    assert await storage.get("workspaces/a/file.bin") == b"data"
    assert b"".join([chunk async for chunk in storage.stream("workspaces/a/file.bin")]) == b"data"
    for key in ("../outside", "/abs/path", "a/../../b", "bad key"):
        with pytest.raises(ValueError, match="storage key"):
            await storage.put(key, b"x", "text/plain")
    await storage.put("workspaces/a/other.bin", b"2", "text/plain")
    assert await storage.delete_prefix("workspaces/a") == 2
    with pytest.raises(NotFoundError):
        await storage.get("workspaces/a/file.bin")


async def test_files_move_in_and_out_of_storage(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "files")
    source = tmp_path / "in.txt"
    source.write_text("payload")
    await storage.put_file("k/in.txt", source, "text/plain")
    target = tmp_path / "out.txt"
    await storage.get_file("k/in.txt", target)
    assert target.read_text() == "payload"


def test_storage_keys_group_by_workspace_and_repository() -> None:
    workspace, repository, snapshot = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    prefix = repository_prefix(workspace, repository)
    assert prefix.startswith(f"workspaces/{workspace}/")
    assert mirror_key(workspace, repository).startswith(prefix)
    assert upload_key(workspace, repository, snapshot, ".zip").startswith(prefix)


def test_the_backend_follows_the_settings(tmp_path: Path) -> None:
    assert isinstance(
        build_storage(Settings(storage_backend="local", storage_dir=tmp_path)), LocalStorage
    )
    assert isinstance(build_queue(Settings(queue_backend="inline")), InlineQueue)


def test_jobs_encode_as_ids_only() -> None:
    job = Job(JobType.RUN_TASK, uuid.uuid4(), uuid.uuid4())
    body = job.encode()
    assert str(job.workspace_id) in body and "description" not in body
    assert Job.decode(body) == job


async def test_the_inline_queue_runs_jobs_in_the_background() -> None:
    queue = InlineQueue()
    seen: list[Job] = []

    async def handler(job: Job) -> bool:
        seen.append(job)
        return True

    queue.bind(handler)
    job = Job(JobType.INDEX_SNAPSHOT, uuid.uuid4(), uuid.uuid4())
    await queue.enqueue(job)
    await queue.drain()
    assert seen == [job]
    assert await queue.backlog() == 0


async def test_an_inline_job_that_raises_does_not_take_the_queue_down() -> None:
    queue = InlineQueue()

    async def handler(job: Job) -> bool:
        raise RuntimeError("boom")

    queue.bind(handler)
    await queue.enqueue(Job(JobType.RUN_TESTS, uuid.uuid4(), uuid.uuid4()))
    await queue.drain()
