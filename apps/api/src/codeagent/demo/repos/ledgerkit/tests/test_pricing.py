from decimal import Decimal

import pytest

from ledgerkit.money import Money
from ledgerkit.pricing import apply_discount, volume_discount


def test_no_discount_below_the_threshold():
    assert apply_discount(Money.of("999.99")) == Money.of("999.99")


def test_discount_above_the_threshold():
    assert apply_discount(Money.of("2000.00")) == Money.of("1900.00")


def test_discount_applies_at_threshold():
    # "Orders of at least 1,000" includes an order of exactly 1,000.
    assert apply_discount(Money.of("1000.00")) == Money.of("950.00")


def test_custom_threshold_and_rate():
    discounted = apply_discount(Money.of("500.00"), threshold=Money.of("400.00"), rate=Decimal("0.10"))
    assert discounted == Money.of("450.00")


@pytest.mark.parametrize(
    ("quantity", "rate"),
    [(1, "0"), (9, "0"), (10, "0.05"), (49, "0.05"), (50, "0.10"), (100, "0.15"), (250, "0.15")],
)
def test_volume_discount_tiers(quantity, rate):
    assert volume_discount(quantity) == Decimal(rate)


def test_negative_quantities_are_rejected():
    with pytest.raises(ValueError):
        volume_discount(-1)
