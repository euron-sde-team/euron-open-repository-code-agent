"""Invoices: line items, subtotal, discounts, tax and total."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ledgerkit.money import Money
from ledgerkit.pricing import apply_discount, volume_discount
from ledgerkit.tax import calc_tax


@dataclass(frozen=True)
class LineItem:
    description: str
    quantity: int
    unit_price: Money

    def amount(self) -> Money:
        """Quantity times unit price, less the volume discount for this quantity."""
        gross = self.unit_price.times(self.quantity)
        return gross - gross.times(volume_discount(self.quantity))


@dataclass
class Invoice:
    customer: str
    region: str
    currency: str = "EUR"
    lines: list[LineItem] = field(default_factory=list)

    def add_line(self, description: str, quantity: int, unit_price: Money) -> LineItem:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if unit_price.currency != self.currency:
            raise ValueError(f"invoice is in {self.currency}, line is in {unit_price.currency}")
        line = LineItem(description, quantity, unit_price)
        self.lines.append(line)
        return line

    def subtotal(self) -> Money:
        total = Money.zero(self.currency)
        for line in self.lines:
            total = total + line.amount()
        return total

    def discounted_subtotal(self) -> Money:
        return apply_discount(self.subtotal())

    def tax(self) -> Money:
        return calc_tax(self.discounted_subtotal(), self.region)

    def total(self) -> Money:
        """What the customer pays: the discounted subtotal plus tax."""
        return self.discounted_subtotal() + self.tax()

    def savings(self) -> Money:
        return self.subtotal() - self.discounted_subtotal()

    def effective_tax_rate(self) -> Decimal:
        return self.tax().ratio(self.discounted_subtotal())
