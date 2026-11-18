"""Choosing who buys.

Rules, in order:
  1. Only volunteers physically at that office today (visitors from the other office count).
  2. Never someone who already holds an open offer or commitment.
  3. Never someone already passed over for this refill (declined / timed out).
Then rank fairly:
  a. people who are NOT currently waiting on a reimbursement first (don't pile more debt on them),
  b. fewest refills bought in the lookback window,
  c. longest since their last refill,
  d. volunteer id, so the choice is deterministic and testable.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from .models import Refill, RefillState, Volunteer
from .ports import AvailabilityPort

_NEVER = datetime.min.replace(tzinfo=timezone.utc)

OUT_OF_POCKET_STATES = {RefillState.NEEDS_REVIEW, RefillState.PURCHASED, RefillState.CLAIM_SUBMITTED}


def rank_candidates(
    office_id: str,
    day: date,
    volunteers: Iterable[Volunteer],
    availability: AvailabilityPort,
    refills: Iterable[Refill],
    since: datetime,
    exclude: set[str],
) -> list[Volunteer]:
    refills = list(refills)
    busy: set[str] = set()
    out_of_pocket: set[str] = set()
    recent_count: dict[str, int] = {}
    last_bought: dict[str, datetime] = {}

    for r in refills:
        if r.state == RefillState.COMMITTED and r.buyer_id:
            busy.add(r.buyer_id)
        if r.state == RefillState.SEEKING_BUYER and r.offered_to:
            busy.add(r.offered_to)
        if r.state in OUT_OF_POCKET_STATES and r.buyer_id:
            out_of_pocket.add(r.buyer_id)
        if r.purchase and r.buyer_id:
            at = r.purchase.purchased_at
            if at >= since:
                recent_count[r.buyer_id] = recent_count.get(r.buyer_id, 0) + 1
            if at > last_bought.get(r.buyer_id, _NEVER):
                last_bought[r.buyer_id] = at

    eligible = [
        v
        for v in volunteers
        if availability.office_on(v.id, day) == office_id and v.id not in busy and v.id not in exclude
    ]
    return sorted(
        eligible,
        key=lambda v: (
            v.id in out_of_pocket,
            recent_count.get(v.id, 0),
            last_bought.get(v.id, _NEVER),
            v.id,
        ),
    )
