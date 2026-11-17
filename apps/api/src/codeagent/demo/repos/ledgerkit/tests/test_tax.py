from decimal import Decimal

import pytest

from ledgerkit.money import Money
from ledgerkit.tax import calc_tax, rate_for, tax_breakdown


def test_rate_for_known_regions():
    assert rate_for("de") == Decimal("0.19")
    assert rate_for("US-CA") == Decimal("0.0725")


def test_unknown_regions_are_an_error():
    with pytest.raises(ValueError, match="no tax rate"):
        rate_for("XX")


def test_calc_tax_rounds_to_cents():
    assert calc_tax(Money.of("100.00"), "DE") == Money.of("19.00")
    assert calc_tax(Money.of("19.99"), "US-CA") == Money.of("1.45")


def test_tax_breakdown_strings():
    breakdown = tax_breakdown(Money.of("200.00"), "FR")
    assert breakdown == {
        "subtotal": "EUR 200.00",
        "rate": "20.00%",
        "tax": "EUR 40.00",
        "total": "EUR 240.00",
    }
