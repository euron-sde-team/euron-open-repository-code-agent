from decimal import Decimal

import pytest

from ledgerkit.money import Money


def test_amounts_are_rounded_to_cents():
    assert Money.of("10.005").amount == Decimal("10.00")
    assert Money.of("10.015").amount == Decimal("10.02")


def test_addition_and_subtraction():
    assert Money.of("10.50") + Money.of("0.75") == Money.of("11.25")
    assert Money.of("10.50") - Money.of("0.75") == Money.of("9.75")


def test_currencies_do_not_mix():
    with pytest.raises(ValueError, match="cannot combine"):
        Money.of("1", "EUR") + Money.of("1", "USD")


def test_times_rounds_the_product():
    assert Money.of("19.99").times(3) == Money.of("59.97")
    assert Money.of("100.00").times(Decimal("0.0725")) == Money.of("7.25")


def test_allocate_splits_without_losing_cents():
    parts = Money.of("100.00").allocate(3)
    assert [p.amount for p in parts] == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum((p.amount for p in parts), Decimal("0")) == Decimal("100.00")


def test_allocate_needs_at_least_one_part():
    with pytest.raises(ValueError):
        Money.of("1").allocate(0)


def test_ratio():
    assert Money.of("25").ratio(Money.of("100")) == Decimal("0.25")
    assert Money.of("25").ratio(Money.zero()) == Decimal("0")


def test_format():
    assert str(Money.of("1234.5")) == "EUR 1,234.50"
