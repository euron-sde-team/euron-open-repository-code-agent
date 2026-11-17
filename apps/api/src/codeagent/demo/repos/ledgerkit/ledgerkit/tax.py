"""Sales tax by region."""

from __future__ import annotations

from decimal import Decimal

from ledgerkit.money import Money

# VAT or sales tax rates by region code. Rates change rarely; when they do, they change
# here and nowhere else.
TAX_RATES: dict[str, Decimal] = {
    "DE": Decimal("0.19"),
    "FR": Decimal("0.20"),
    "NL": Decimal("0.21"),
    "IE": Decimal("0.23"),
    "US-CA": Decimal("0.0725"),
    "US-NY": Decimal("0.04"),
}


def rate_for(region: str) -> Decimal:
    """The tax rate for a region code; unknown regions are an error, not zero tax."""
    try:
        return TAX_RATES[region.upper()]
    except KeyError:
        raise ValueError(f"no tax rate for region {region!r}") from None


def calc_tax(subtotal: Money, region: str) -> Money:
    """The tax owed on a subtotal in a region, rounded to cents."""
    return subtotal.times(rate_for(region))


def tax_breakdown(subtotal: Money, region: str) -> dict[str, str]:
    """Subtotal, rate, tax and total as display strings, for invoices and receipts."""
    tax = calc_tax(subtotal, region)
    return {
        "subtotal": subtotal.format(),
        "rate": f"{rate_for(region) * 100:.2f}%",
        "tax": tax.format(),
        "total": (subtotal + tax).format(),
    }
