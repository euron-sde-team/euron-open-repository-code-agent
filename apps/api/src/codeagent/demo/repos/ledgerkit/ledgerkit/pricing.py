"""Discounts: a threshold discount for large orders and volume pricing for quantities."""

from __future__ import annotations

from decimal import Decimal

from ledgerkit.money import Money

DISCOUNT_THRESHOLD = Money.of("1000.00")
DISCOUNT_RATE = Decimal("0.05")
VOLUME_TIERS: tuple[tuple[int, Decimal], ...] = (
    (100, Decimal("0.15")),
    (50, Decimal("0.10")),
    (10, Decimal("0.05")),
)


def apply_discount(
    subtotal: Money, threshold: Money = DISCOUNT_THRESHOLD, rate: Decimal = DISCOUNT_RATE
) -> Money:
    """Take `rate` off orders of at least `threshold`."""
    if subtotal.amount > threshold.amount:
        return subtotal - subtotal.times(rate)
    return subtotal


def volume_discount(quantity: int) -> Decimal:
    """The discount rate for buying `quantity` units of one item."""
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    for minimum, rate in VOLUME_TIERS:
        if quantity >= minimum:
            return rate
    return Decimal("0")
