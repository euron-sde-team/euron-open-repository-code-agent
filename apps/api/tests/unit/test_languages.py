from __future__ import annotations

import pytest

from codeagent.codeintel.languages import (
    detect_language,
    is_test_path,
    is_vendored,
    looks_binary,
)


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("app/main.py", "Python"),
        ("web/src/App.tsx", "TSX"),
        ("web/src/index.ts", "TypeScript"),
        ("lib/util.js", "JavaScript"),
        ("cmd/server/main.go", "Go"),
        ("Dockerfile", "Dockerfile"),
        ("Makefile", "Makefile"),
        ("README.md", "Markdown"),
        ("pyproject.toml", "TOML"),
    ],
)
def test_language_comes_from_the_extension_or_file_name(path: str, language: str) -> None:
    assert detect_language(path) == language


def test_shebang_decides_when_there_is_no_extension() -> None:
    assert detect_language("bin/run", "#!/usr/bin/env python3\nprint('x')") == "Python"


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_money.py",
        "pkg/money_test.py",
        "pkg/test_money.py",
        "web/cart.test.ts",
        "web/cart.spec.ts",
        "limiter/limiter_test.go",
    ],
)
def test_test_files_are_recognised(path: str) -> None:
    assert is_test_path(path)


@pytest.mark.parametrize("path", ["ledgerkit/money.py", "src/cart.ts", "latest.py", "contest.go"])
def test_ordinary_files_are_not_tests(path: str) -> None:
    assert not is_test_path(path)


@pytest.mark.parametrize(
    "path",
    ["node_modules/react/index.js", "vendor/lib/x.go", "dist/app.js", "a/.venv/b.py", "x.min.js"],
)
def test_vendored_and_generated_paths_are_skipped(path: str) -> None:
    assert is_vendored(path)


def test_source_paths_are_not_vendored() -> None:
    assert not is_vendored("src/vendorish/thing.py")


def test_a_nul_byte_marks_a_file_binary() -> None:
    assert looks_binary(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert not looks_binary(b"plain text\nwith lines\n")
