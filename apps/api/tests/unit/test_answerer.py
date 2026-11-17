"""The local answerer: intents, grounding and the refusal to guess."""

from __future__ import annotations

import uuid

import pytest

from codeagent.ai.answerer import NOT_FOUND, AnswerRequest, Intent, classify, compose
from codeagent.ai.sources import CodeSource, Location, SymbolFacts


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Who calls apply_discount?", Intent.USAGES),
        ("Where is calc_tax used?", Intent.USAGES),
        ("Which tests cover apply_discount?", Intent.TESTS),
        ("Is volume_discount tested?", Intent.TESTS),
        ("What does apply_discount do and which tests cover it?", Intent.EXPLAIN),
        ("Explain Invoice.total", Intent.EXPLAIN),
        ("Where is Money defined?", Intent.DEFINITION),
        ("Find the tax module", Intent.DEFINITION),
        ("How are invoices exported?", Intent.OVERVIEW),
    ],
)
def test_questions_are_classified_by_what_they_ask(question: str, intent: Intent) -> None:
    assert classify(question) is intent


def source(
    n: int, path: str, start: int, end: int, text: str, name: str | None = None
) -> CodeSource:
    return CodeSource(
        repository_id=uuid.uuid4(),
        repository="ledgerkit",
        file_id=uuid.uuid4(),
        path=path,
        language="Python",
        start_line=start,
        end_line=end,
        text=text,
        symbol_id=uuid.uuid4() if name else None,
        symbol_name=name,
        qualified_name=f"ledgerkit.{name}" if name else None,
        n=n,
    )


def fact(src: CodeSource, **kwargs: object) -> SymbolFacts:
    assert src.symbol_id is not None and src.symbol_name is not None
    return SymbolFacts(
        symbol_id=src.symbol_id,
        name=src.symbol_name,
        qualified_name=src.qualified_name or src.symbol_name,
        kind="function",
        path=src.path,
        start_line=src.start_line,
        end_line=src.end_line,
        signature=f"def {src.symbol_name}(x)",
        doc="Take a rate off large orders.",
        **kwargs,  # type: ignore[arg-type]
    )


DISCOUNT = source(1, "ledgerkit/pricing.py", 18, 24, "def apply_discount(x): ...", "apply_discount")
CALLER = Location("Invoice.discounted_subtotal", "ledgerkit/invoice.py", 48)


def test_an_explanation_lists_signature_callers_and_cites_the_definition() -> None:
    discount = fact(DISCOUNT, callers=[CALLER], tests=[Location("test_a", "tests/t.py", 5)])
    text = compose(
        AnswerRequest("What does apply_discount do?", [DISCOUNT], [discount], [discount.symbol_id])
    )
    assert "apply_discount" in text
    assert "[1]" in text
    assert "Take a rate off large orders." in text
    assert "Called by" in text and "Invoice.discounted_subtotal" in text
    assert "Tests" in text


def test_usage_answers_cite_only_places_inside_the_given_sources() -> None:
    caller_source = source(2, "ledgerkit/invoice.py", 45, 52, "def discounted_subtotal(): ...")
    discount = fact(DISCOUNT, callers=[CALLER, Location("far_away", "other/elsewhere.py", 3)])
    text = compose(
        AnswerRequest(
            "Who calls apply_discount?",
            [DISCOUNT, caller_source],
            [discount],
            [discount.symbol_id],
        )
    )
    assert "ledgerkit/invoice.py" in text and "[2]" in text
    far = next(line for line in text.splitlines() if "other/elsewhere.py" in line)
    assert "[" not in far.split("line 3")[-1]


def test_a_missing_test_is_reported_not_invented() -> None:
    discount = fact(DISCOUNT)
    text = compose(
        AnswerRequest(
            "Which tests cover apply_discount?", [DISCOUNT], [discount], [discount.symbol_id]
        )
    )
    assert "No test references" in text


def test_no_sources_means_not_found() -> None:
    assert compose(AnswerRequest("anything", [])) == NOT_FOUND


def test_sources_that_share_nothing_with_the_question_are_not_an_answer() -> None:
    unrelated = source(1, "tests/test_money.py", 3, 6, "def test_rounding(): assert True")
    assert compose(AnswerRequest("xyzzy plugh frobnicate quantum", [unrelated])) == NOT_FOUND


def test_an_open_question_lists_the_most_relevant_places() -> None:
    export = source(
        1,
        "ledgerkit/export.py",
        27,
        33,
        "def invoice_to_csv(invoice): ...",
        "export.invoice_to_csv",
    )
    text = compose(AnswerRequest("How are invoices exported to CSV?", [export]))
    assert "ledgerkit/export.py" in text and "[1]" in text
