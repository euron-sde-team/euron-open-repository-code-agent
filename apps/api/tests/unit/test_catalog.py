"""Every helper in the offline catalog must pass its own tests, exactly as rendered."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from codeagent.agent import catalog


@pytest.mark.parametrize("helper", catalog.HELPERS, ids=lambda h: h.name)
def test_the_helper_and_its_tests_pass_together(helper: catalog.Helper, tmp_path: Path) -> None:
    source = "\n".join(helper.imports) + "\n\n" + helper.render_source(helper.name)
    (tmp_path / "helper_module.py").write_text(source)
    tests = (
        "\n".join([f"from helper_module import {helper.name}", *helper.test_imports])
        + "\n\n"
        + helper.render_tests(helper.name)
    )
    (tmp_path / "test_helper.py").write_text(tests)
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_helper.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_lookup_accepts_aliases_and_ignores_case() -> None:
    assert catalog.find("CLAMP") is not None
    assert catalog.find("not-a-helper") is None


def test_names_are_unique() -> None:
    names = catalog.names()
    assert len(names) == len(set(names)) >= 10
