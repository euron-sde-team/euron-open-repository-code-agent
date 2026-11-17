"""Fixtures shared by every suite: the bundled sample repositories."""

from __future__ import annotations

from pathlib import Path

import pytest

from codeagent.codeintel.builder import IndexBuild, build_index

REPOS = Path(__file__).resolve().parents[1] / "src" / "codeagent" / "demo" / "repos"


def repo_sources(name: str) -> list[tuple[str, bytes, int]]:
    base = REPOS / name
    return [
        (path.relative_to(base).as_posix(), path.read_bytes(), path.stat().st_size)
        for path in sorted(base.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]


def build_repo(name: str) -> IndexBuild:
    return build_index(repo_sources(name), max_file_bytes=512 * 1024, chunk_max_lines=60)


@pytest.fixture(scope="session")
def ledgerkit() -> IndexBuild:
    return build_repo("ledgerkit")


@pytest.fixture(scope="session")
def ratelimit() -> IndexBuild:
    return build_repo("ratelimit")


@pytest.fixture(scope="session")
def checkout_web() -> IndexBuild:
    return build_repo("checkout-web")
