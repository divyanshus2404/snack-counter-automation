"""Domain data: offices, volunteers and the Refill record that moves through the lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo

from .money import Money


@dataclass(frozen=True)
class Office:
    id: str
    name: str
    currency: str
    timezone: str
    monthly_budget: Money
    min_purchase: Money  # below this a refill is not worth starting
    max_purchase: Money  # default spending cap handed to a buyer
    chat_channel: str
    admin_chat_id: str  # office coordinator: budget exceptions, escalations

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def local_date(self, at: datetime) -> date:
        return at.astimezone(self.tz).date()


@dataclass(frozen=True)
class Volunteer:
    id: str
    name: str
    employee_id: str  # ID the HR system knows
    chat_id: str
    home_office: str
    payroll_currency: str  # HR pays out in this; we only record it


class RefillState(str, Enum):
    WAITING_FOR_BUDGET = "waiting_for_budget"  # month's budget used up; resumes next month
    SEEKING_BUYER = "seeking_buyer"            # offer out to one person, or broadcast to the office
    COMMITTED = "committed"                    # exactly one buyer, with a deadline and spending cap
    NEEDS_REVIEW = "needs_review"              # receipt over the cap; coordinator must approve
    PURCHASED = "purchased"                    # receipt recorded; claim not yet accepted by HR
    CLAIM_SUBMITTED = "claim_submitted"        # waiting for HR approval (1-10 days)
    REIMBURSED = "reimbursed"                  # HR approved - done
    CLAIM_REJECTED = "claim_rejected"          # HR said no - coordinator follows up by hand


ACTIVE_STATES = {
    RefillState.WAITING_FOR_BUDGET,
    RefillState.SEEKING_BUYER,
    RefillState.COMMITTED,
}
# States where money has actually been spent and counts as the office's spend.
SPENT_STATES = {
    RefillState.NEEDS_REVIEW,
    RefillState.PURCHASED,
    RefillState.CLAIM_SUBMITTED,
    RefillState.REIMBURSED,
}
# States holding a budget reservation (the cap) but no actual spend yet.
RESERVED_STATES = {RefillState.SEEKING_BUYER, RefillState.COMMITTED}


@dataclass
class Purchase:
    amount: Money
    receipt_image: bytes
    items: list[str]
    purchased_at: datetime


@dataclass
class Refill:
    id: str
    office_id: str
    reported_by: str
    reported_at: datetime
    state: RefillState
    spend_cap: Optional[Money] = None
    # buyer search
    offered_to: Optional[str] = None
    offer_expires_at: Optional[datetime] = None
    broadcast: bool = False
    broadcast_escalated: bool = False
    passed_over: set[str] = field(default_factory=set)  # declined or timed out
    # commitment
    buyer_id: Optional[str] = None
    buy_deadline: Optional[datetime] = None
    # outcome
    purchase: Optional[Purchase] = None
    claim_id: Optional[str] = None
    claim_submitted_at: Optional[datetime] = None
    claim_nudged: bool = False
    resolved_at: Optional[datetime] = None
    history: list[tuple[datetime, str]] = field(default_factory=list)

    def log(self, at: datetime, event: str) -> None:
        self.history.append((at, event))

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES


@dataclass(frozen=True)
class Timeouts:
    offer_response: timedelta = timedelta(hours=2)
    buy_deadline: timedelta = timedelta(hours=24)
    broadcast_escalation: timedelta = timedelta(hours=4)
    claim_nudge_after: timedelta = timedelta(days=7)
    lookback_for_fairness: timedelta = timedelta(days=90)
