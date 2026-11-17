"""Working trees in the worker: a repository's mirror restored into a scratch directory."""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio

from codeagent.core.errors import NotFoundError
from codeagent.integrations import git
from codeagent.integrations.storage import Storage
from codeagent.models import Repository


async def restore_mirror(storage: Storage, repository: Repository, dest: Path) -> None:
    if not repository.mirror_key:
        raise NotFoundError("The repository has not been imported yet.")
    archive = dest.parent / f"{dest.name}.tar.gz"
    await storage.get_file(repository.mirror_key, archive)
    try:
        await anyio.to_thread.run_sync(git.unpack, archive, dest)
    finally:
        archive.unlink(missing_ok=True)


async def store_mirror(storage: Storage, repository: Repository, tree: Path, key: str) -> None:
    archive = tree.parent / f"{tree.name}-mirror.tar.gz"
    await anyio.to_thread.run_sync(git.pack, tree, archive)
    try:
        await storage.put_file(key, archive, "application/gzip")
    finally:
        archive.unlink(missing_ok=True)


@asynccontextmanager
async def checkout(
    storage: Storage, repository: Repository, commit: str | None
) -> AsyncIterator[Path]:
    """The repository at `commit` (its mirror's HEAD when None), deleted afterwards."""
    with git.scratch_dir("tree") as scratch:
        tree = Path(scratch) / "tree"
        await restore_mirror(storage, repository, tree)
        if commit:
            await git.checkout(tree, commit)
        yield tree


def copy_tree(source: Path, dest: Path) -> None:
    """A copy of a working tree without its .git directory, for a sandbox run."""
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(".git"), symlinks=True)
