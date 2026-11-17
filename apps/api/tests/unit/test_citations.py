from __future__ import annotations

import uuid

from codeagent.ai.citations import extract_citations
from codeagent.ai.sources import CodeSource


def source(n: int, path: str, start: int, end: int) -> CodeSource:
    return CodeSource(
        repository_id=uuid.uuid4(),
        repository="ledgerkit",
        file_id=uuid.uuid4(),
        path=path,
        language="Python",
        start_line=start,
        end_line=end,
        text="\n".join(f"line {i}" for i in range(start, end + 1)),
        qualified_name="ledgerkit.pricing.apply_discount",
        n=n,
    )


SOURCES = [source(1, "ledgerkit/pricing.py", 18, 24), source(2, "tests/test_pricing.py", 5, 9)]


def test_valid_markers_become_citations_with_lines() -> None:
    text, citations = extract_citations("It lives in pricing [1] and is tested [2].", SOURCES)
    assert text == "It lives in pricing [1] and is tested [2]."
    assert [c["n"] for c in citations] == [1, 2]
    assert citations[0]["path"] == "ledgerkit/pricing.py"
    assert (citations[0]["start_line"], citations[0]["end_line"]) == (18, 24)
    assert citations[0]["snippet"].startswith("line 18")


def test_markers_for_unknown_sources_are_removed() -> None:
    text, citations = extract_citations("Real [1] but invented [7].", SOURCES)
    assert "[7]" not in text
    assert [c["n"] for c in citations] == [1]


def test_grouped_markers_keep_only_the_valid_numbers() -> None:
    text, citations = extract_citations("Both [1, 2, 9].", SOURCES)
    assert text == "Both [1] [2]."
    assert [c["n"] for c in citations] == [1, 2]


def test_indexing_inside_code_blocks_is_not_a_citation() -> None:
    answer = "Use it like this:\n```python\nitems[1]\n```\nSee [2]."
    text, citations = extract_citations(answer, SOURCES)
    assert "items[1]" in text
    assert [c["n"] for c in citations] == [2]


def test_an_answer_without_markers_has_no_citations() -> None:
    assert extract_citations("Nothing to cite.", SOURCES) == ("Nothing to cite.", [])
