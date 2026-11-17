"""Money: a Decimal amount and a currency, rounded to cents on every operation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")
DEFAULT_CURRENCY = "EUR"


@dataclass(frozen=True)
class Money:
    """An amount in one currency. Arithmetic between currencies is an error."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    @classmethod
    def of(cls, value: str | int | Decimal, currency: str = DEFAULT_CURRENCY) -> Money:
        """Build Money from a string or integer, never from a float."""
        return cls(Decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN), currency)

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Money:
        return cls(Decimal("0.00"), currency)

    def _check(self, other: Money) -> None:
        if other.currency != self.currency:
            raise ValueError(f"cannot combine {self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def times(self, factor: int | Decimal) -> Money:
        """Multiply by a quantity or a rate, rounding the result to cents."""
        product = self.amount * Decimal(factor)
        return Money(product.quantize(CENT, rounding=ROUND_HALF_EVEN), self.currency)

    def ratio(self, other: Money) -> Decimal:
        """This amount as a fraction of another, for reports and percentages."""
        self._check(other)
        if other.amount == 0:
            return Decimal("0")
        return self.amount / other.amount

    def allocate(self, parts: int) -> list[Money]:
        """Split into `parts` amounts that differ by at most one cent and sum exactly."""
        if parts < 1:
            raise ValueError("parts must be at least 1")
        cents = int(self.amount / CENT)
        base, remainder = divmod(cents, parts)
        return [
            Money(Decimal(base + (1 if i < remainder else 0)) * CENT, self.currency)
            for i in range(parts)
        ]

    def format(self) -> str:
        return f"{self.currency} {self.amount:,.2f}"

    def __str__(self) -> str:
        return self.format()
