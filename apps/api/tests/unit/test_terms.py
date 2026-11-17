from __future__ import annotations

import pytest

from codeagent.codeintel.terms import identifiers, split_identifier, stem, terms, words


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("parseHTTPResponse", ["parse", "http", "response"]),
        ("calc_tax_v2", ["calc", "tax", "v2"]),
        ("CartSummary", ["cart", "summary"]),
        ("DEFAULT_BURST", ["default", "burst"]),
        ("x", ["x"]),
    ],
)
def test_identifiers_are_split_into_words(name: str, parts: list[str]) -> None:
    assert split_identifier(name) == parts


def test_stemming_folds_inflections() -> None:
    assert stem("discounts") == stem("discount")
    assert stem("calculating") == stem("calculate") or stem("calculating").startswith("calcul")


def test_terms_drop_stop_words_and_keywords() -> None:
    result = terms("Where is the tax calculated for the invoice?")
    assert "the" not in result
    assert any(t.startswith("tax") for t in result)
    assert any(t.startswith("invoic") for t in result)


def test_terms_cover_identifiers_in_code() -> None:
    assert "discount" in terms("def apply_discount(subtotal):") or any(
        t.startswith("discount") for t in terms("def apply_discount(subtotal):")
    )


def test_identifiers_pick_out_code_like_words_from_a_question() -> None:
    found = identifiers("What does apply_discount do, and is Invoice.total tested?")
    assert "apply_discount" in found
    assert "Invoice" in found or "Invoice.total" in found


def test_words_lowercases() -> None:
    assert words("Hello World") == ["hello", "world"]
