"""The data: money, offices, volunteers and a refill."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class CurrencyMismatch(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    """An exact amount in one currency. NOK and INR can never be mixed by accident."""

    amount: Decimal
    currency: str

    def __post_init__(self):
        object.__setattr__(self, "amount", Decimal(str(self.amount)).quantize(Decimal("0.01")))

    def _same_currency(self, other: Money):
        if self.currency != other.currency:
            raise CurrencyMismatch(f"cannot mix {self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount < other.amount

    def __gt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount > other.amount

    def convert(self, currency: str, rate: Decimal) -> Money:
        """1 unit of my currency = `rate` units of `currency`."""
        return Money(self.amount * Decimal(str(rate)), currency)

    def __str__(self):
        return f"{self.amount:,.2f} {self.currency}"


@dataclass(frozen=True)
class Office:
    id: str
    name: str
    currency: str
    monthly_budget: Money
    max_purchase: Money  # spending cap for one refill
    channel: str  # office chat channel


@dataclass(frozen=True)
class Volunteer:
    id: str
    name: str
    employee_id: str  # the ID the HR system knows


class State(str, Enum):
    LOOKING_FOR_BUYER = "looking_for_buyer"
    BUYER_COMMITTED = "buyer_committed"
    CLAIM_SENT = "claim_sent"
    REIMBURSED = "reimbursed"


@dataclass
class Refill:
    id: str
    office_id: str
    state: State
    cap: Money
    # while looking for a buyer
    asked: Optional[str] = None  # volunteer currently asked
    answer_by: Optional[datetime] = None
    open_to_all: bool = False  # nobody left to ask -> first to accept gets it
    skipped: set[str] = field(default_factory=set)  # declined or didn't answer
    # once someone commits
    buyer: Optional[str] = None
    buy_by: Optional[datetime] = None
    # once bought
    amount: Optional[Money] = None
    bought_at: Optional[datetime] = None
    claim_id: Optional[str] = None


OSLO = Office("oslo", "Oslo", "NOK", Money(6000, "NOK"), Money(1200, "NOK"), "#snacks-oslo")
BENGALURU = Office("blr", "Bengaluru", "INR", Money(15000, "INR"), Money(3000, "INR"), "#snacks-bengaluru")
