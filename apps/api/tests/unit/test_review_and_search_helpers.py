from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from codeagent import __version__
from codeagent.core.errors import UnprocessableError
from codeagent.models import Patch, Task, User, Workspace
from codeagent.models.enums import Role
from codeagent.services.principal import Principal
from codeagent.services.retrieval import keyword_query
from codeagent.services.review import branch_name, commit_message, mbox
from codeagent.services.search import glob_to_like, match_ranges, validate_regex
from codeagent.services.tasks import can_decide


def task(number: int = 12, title: str = "Fix the failing pricing test", **kwargs: object) -> Task:
    return Task(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        number=number,
        title=title,
        status="awaiting_review",
        **kwargs,
    )  # type: ignore[arg-type]


def patch() -> Patch:
    return Patch(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        revision=2,
        status="proposed",
        summary="Include the boundary",
        rationale="An order of exactly 1,000 should be discounted.\n\n\n\nThe test says so.",
        diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n",
        files=[{"path": "a.py", "change_type": "modified", "additions": 1, "deletions": 1}],
        additions=1,
        deletions=1,
        planner="local",
        skill="fix_test",
        created_at=datetime(2026, 11, 3, 9, 30, tzinfo=UTC),
    )


def person(name: str, email: str) -> User:
    return User(id=uuid.uuid4(), name=name, email=email, password_hash="x")


def test_branch_names_carry_the_number_and_a_slug() -> None:
    assert branch_name(task(7, "Rename apply_discount to apply_threshold_discount!")) == (
        "codeagent/7-rename-apply-discount-to-apply-threshold"
    )
    assert branch_name(task(3, "???")).startswith("codeagent/3-")


def test_the_commit_message_has_title_rationale_and_trailers() -> None:
    message = commit_message(
        task(),
        patch(),
        person("Sofia Alvarez", "sofia@example.com"),
        person("Priya", "priya@example.com"),
    )
    subject, _, rest = message.partition("\n\n")
    assert subject == "Fix the failing pricing test"
    assert "\n\n\n" not in message
    assert "CodeAgent-Task: #12" in rest
    assert "Requested-by: Sofia Alvarez <sofia@example.com>" in rest
    assert "Approved-by: Priya <priya@example.com>" in rest


def test_the_patch_export_is_an_mbox_message_git_am_accepts() -> None:
    t, p = task(), patch()
    text = mbox(t, p, commit_message(t, p, None, None))
    assert text.startswith("From ")
    assert "Subject: [PATCH] Fix the failing pricing test" in text
    assert "1 file changed, 1 insertion(+), 1 deletion(-)" in text
    assert "\n+b\n" in text
    assert text.rstrip().endswith("codeagent " + __version__)


def test_regex_search_refuses_catastrophic_and_invalid_patterns() -> None:
    validate_regex(r"def \w+_discount\(")
    for pattern in (r"(a+)+$", r"(\w*)*x", "(unclosed", "x" * 300):
        with pytest.raises(UnprocessableError):
            validate_regex(pattern)


def test_path_globs_become_like_patterns_with_escaping() -> None:
    assert glob_to_like("src/**/*.py") == "src/%/%.py"
    assert glob_to_like("pricing") == "%pricing%"
    assert glob_to_like("100%_done") == "%100\\%\\_done%"
    assert glob_to_like("a?.py") == "a_.py"


def test_match_ranges_cover_every_occurrence() -> None:
    assert match_ranges("Money money MONEY", "money", regex=False, case_sensitive=False) == [
        (0, 5),
        (6, 11),
        (12, 17),
    ]
    assert match_ranges("Money money", "money", regex=False, case_sensitive=True) == [(6, 11)]
    assert match_ranges("a1 b22", r"\d+", regex=True, case_sensitive=False) == [(1, 2), (4, 6)]


def test_the_keyword_query_ors_the_stemmed_terms() -> None:
    query = keyword_query("Where is the tax calculated for an invoice?")
    assert query is not None
    assert " | " in query
    assert keyword_query("?!") is None


def decision_workspace(independent: bool) -> Workspace:
    return Workspace(
        id=uuid.uuid4(), slug="w", name="W", settings={"require_independent_review": independent}
    )


def test_only_a_maintainer_can_decide_a_proposed_patch() -> None:
    requester = person("R", "r@example.com")
    t = task(created_by=requester.id)
    proposed = patch()
    principal = Principal(user=requester)
    ws = decision_workspace(False)
    assert can_decide(t, proposed, principal, Role.MAINTAINER, ws)
    assert not can_decide(t, proposed, principal, Role.DEVELOPER, ws)
    assert not can_decide(t, None, principal, Role.OWNER, ws)
    proposed.status = "approved"
    assert not can_decide(t, proposed, principal, Role.OWNER, ws)


def test_independent_review_blocks_the_requester_but_not_others() -> None:
    requester, other = person("R", "r@example.com"), person("O", "o@example.com")
    t = task(created_by=requester.id)
    ws = decision_workspace(True)
    assert not can_decide(t, patch(), Principal(user=requester), Role.OWNER, ws)
    assert can_decide(t, patch(), Principal(user=other), Role.MAINTAINER, ws)
