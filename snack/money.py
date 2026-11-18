"""Money as an exact decimal amount plus a currency code.

Amounts in different currencies can never be added or compared by accident:
the only way to combine NOK and INR is an explicit conversion with a stated rate.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


class CurrencyMismatch(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        amount = Decimal(str(self.amount)).quantize(_CENT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", self.currency.upper())

    @staticmethod
    def zero(currency: str) -> "Money":
        return Money(Decimal(0), currency)

    def _check(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError(f"expected Money, got {type(other).__name__}")
        if other.currency != self.currency:
            raise CurrencyMismatch(f"cannot combine {self.currency} with {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount >= other.amount

    def min(self, other: "Money") -> "Money":
        return self if self <= other else other

    def convert(self, to_currency: str, rate: Decimal) -> "Money":
        """Convert with an explicit rate: 1 unit of self.currency = `rate` units of to_currency."""
        if to_currency.upper() == self.currency:
            return self
        return Money(self.amount * Decimal(str(rate)), to_currency)

    def __str__(self) -> str:
        return f"{self.amount:,.2f} {self.currency}"


def total(items: list[Money], currency: str) -> Money:
    result = Money.zero(currency)
    for m in items:
        result = result + m
    return result
