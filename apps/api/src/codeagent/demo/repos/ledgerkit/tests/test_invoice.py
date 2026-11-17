from decimal import Decimal

import pytest

from ledgerkit.invoice import Invoice
from ledgerkit.money import Money


def make_invoice():
    invoice = Invoice(customer="Acme Robotics", region="DE")
    invoice.add_line("Pick-and-place arm", 2, Money.of("1249.50"))
    invoice.add_line("Service plan", 1, Money.of("180.00"))
    return invoice


def test_subtotal_sums_the_lines():
    assert make_invoice().subtotal() == Money.of("2679.00")


def test_total_includes_discount_and_tax():
    invoice = make_invoice()
    assert invoice.discounted_subtotal() == Money.of("2545.05")
    assert invoice.tax() == Money.of("483.56")
    assert invoice.total() == Money.of("3028.61")


def test_volume_discount_applies_per_line():
    invoice = Invoice(customer="Bulk Buyer", region="NL")
    invoice.add_line("Gripper pads", 50, Money.of("4.00"))
    assert invoice.subtotal() == Money.of("180.00")


def test_lines_must_match_the_invoice_currency():
    invoice = Invoice(customer="Globex", region="US-NY", currency="USD")
    with pytest.raises(ValueError, match="invoice is in USD"):
        invoice.add_line("Sensor", 1, Money.of("10.00", "EUR"))


def test_quantity_must_be_positive():
    with pytest.raises(ValueError):
        make_invoice().add_line("Nothing", 0, Money.of("1.00"))


def test_savings_and_effective_rate():
    invoice = make_invoice()
    assert invoice.savings() == Money.of("133.95")
    assert invoice.effective_tax_rate().quantize(Decimal("0.0001")) == Decimal("0.1900")
