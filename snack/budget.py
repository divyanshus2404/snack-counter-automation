"""Budget check, always in the office's own currency.

remaining = monthly budget
            - actual spend this month (receipts dated this month, office local time)
            - caps reserved by refills that are still looking for / waiting on a buyer

Reserving the cap up front means two refills in flight can never jointly overspend.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import RESERVED_STATES, SPENT_STATES, Office, Refill
from .money import Money, total


def month_key(office: Office, at: datetime) -> tuple[int, int]:
    d = office.local_date(at)
    return d.year, d.month


def spent_in_month(office: Office, refills: Iterable[Refill], year: int, month: int) -> Money:
    return total(
        [
            r.purchase.amount
            for r in refills
            if r.office_id == office.id
            and r.state in SPENT_STATES
            and r.purchase is not None
            and month_key(office, r.purchase.purchased_at) == (year, month)
        ],
        office.currency,
    )


def reserved(office: Office, refills: Iterable[Refill]) -> Money:
    return total(
        [r.spend_cap for r in refills if r.office_id == office.id and r.state in RESERVED_STATES and r.spend_cap],
        office.currency,
    )


def remaining(office: Office, refills: Iterable[Refill], now: datetime, exclude_refill_id: str | None = None) -> Money:
    refills = [r for r in refills if r.id != exclude_refill_id]
    year, month = month_key(office, now)
    return office.monthly_budget - spent_in_month(office, refills, year, month) - reserved(office, refills)


def cap_for_new_refill(office: Office, refills: Iterable[Refill], now: datetime, exclude_refill_id: str | None = None) -> Money | None:
    """Spending cap to give the buyer, or None if there isn't enough budget left to be worth a trip."""
    left = remaining(office, refills, now, exclude_refill_id)
    if left < office.min_purchase:
        return None
    return office.max_purchase.min(left)
