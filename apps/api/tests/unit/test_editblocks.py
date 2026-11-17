from __future__ import annotations

import pytest

from codeagent.agent.editblocks import Edit, EditError, apply_edit, apply_edits, parse

RESPONSE = """PLAN:
1. Change the comparison.
2. Add a test.

RATIONALE:
Orders of exactly the threshold should be discounted.

EDITS:
ledgerkit/pricing.py
<<<<<<< SEARCH
    if subtotal.amount > threshold.amount:
=======
    if subtotal.amount >= threshold.amount:
>>>>>>> REPLACE

tests/test_new.py
<<<<<<< SEARCH
=======
def test_it():
    assert True
>>>>>>> REPLACE
"""


def test_the_three_sections_are_parsed() -> None:
    plan = parse(RESPONSE)
    assert plan.steps == ["Change the comparison.", "Add a test."]
    assert "exactly the threshold" in plan.rationale
    assert [e.path for e in plan.edits] == ["ledgerkit/pricing.py", "tests/test_new.py"]
    assert plan.edits[1].search == ""


def test_an_edit_replaces_text_exactly_once() -> None:
    edit = Edit("a.py", "x = 1\n", "x = 2\n")
    assert apply_edit("y = 0\nx = 1\n", edit) == "y = 0\nx = 2\n"


def test_indentation_differences_are_tolerated_as_a_fallback() -> None:
    edit = Edit("a.py", "x = 1   \n", "x = 2\n")
    assert apply_edit("y = 0\n    x = 1\n", edit).count("x = 2") == 1


def test_a_search_that_is_not_found_fails_and_quotes_the_block() -> None:
    with pytest.raises(EditError) as caught:
        apply_edit("a = 1\n", Edit("a.py", "b = 2\n", "b = 3\n"))
    assert "b = 2" in caught.value.block


def test_an_empty_search_creates_a_file() -> None:
    result = apply_edits({}, [Edit("new.py", "", "VALUE = 1\n")])
    assert result == {"new.py": "VALUE = 1\n"}


def test_an_empty_search_on_an_existing_file_is_refused() -> None:
    with pytest.raises(EditError):
        apply_edits({"a.py": "x\n"}, [Edit("a.py", "", "y\n")])


@pytest.mark.parametrize("path", ["../escape.py", "/etc/passwd", "a/../../b.py"])
def test_unsafe_paths_are_refused(path: str) -> None:
    text = f"EDITS:\n{path}\n<<<<<<< SEARCH\n=======\nx\n>>>>>>> REPLACE\n"
    with pytest.raises(EditError):
        parse(text)
