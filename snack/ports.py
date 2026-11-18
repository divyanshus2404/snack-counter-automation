"""Interfaces to the outside world, plus in-memory stand-ins used by tests and the demo.

The core logic only talks to these ports, so the real chat tool, HR API and
calendar/desk-booking feed can be plugged in later without touching it.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol


# ---------------------------------------------------------------- clock
class Clock(Protocol):
    def now(self) -> datetime: ...


class FakeClock:
    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, at: datetime) -> None:
        self._now = at


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------- chat
class ChatPort(Protocol):
    def send_direct(self, chat_id: str, text: str) -> None: ...
    def post_channel(self, channel: str, text: str) -> None: ...


@dataclass
class ChatMessage:
    to: str  # chat id or channel
    text: str
    direct: bool


class FakeChat:
    """Records messages. In production, buttons in these messages call accept/decline."""

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def send_direct(self, chat_id: str, text: str) -> None:
        self.messages.append(ChatMessage(chat_id, text, True))

    def post_channel(self, channel: str, text: str) -> None:
        self.messages.append(ChatMessage(channel, text, False))

    def to(self, recipient: str) -> list[str]:
        return [m.text for m in self.messages if m.to == recipient]


# ---------------------------------------------------------------- HR
class ClaimStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HRUnavailable(RuntimeError):
    pass


class HRPort(Protocol):
    def submit_claim(
        self,
        employee_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        receipt_image: bytes,
        idempotency_key: str,
    ) -> str: ...

    def claim_status(self, claim_id: str) -> ClaimStatus: ...


@dataclass
class FakeClaim:
    id: str
    employee_id: str
    amount: Decimal
    currency: str
    description: str
    receipt_image: bytes
    status: ClaimStatus = ClaimStatus.PENDING


class FakeHR:
    """Simulates the external HR system. Tests decide when claims are approved."""

    def __init__(self) -> None:
        self.claims: dict[str, FakeClaim] = {}
        self._by_key: dict[str, str] = {}
        self._ids = itertools.count(1)
        self.fail_next_submits = 0

    def submit_claim(self, employee_id, amount, currency, description, receipt_image, idempotency_key):
        if self.fail_next_submits > 0:
            self.fail_next_submits -= 1
            raise HRUnavailable("HR system timed out")
        if idempotency_key in self._by_key:  # a retry must not create a second claim
            return self._by_key[idempotency_key]
        claim_id = f"HR-{next(self._ids)}"
        self.claims[claim_id] = FakeClaim(claim_id, employee_id, Decimal(amount), currency, description, receipt_image)
        self._by_key[idempotency_key] = claim_id
        return claim_id

    def claim_status(self, claim_id: str) -> ClaimStatus:
        return self.claims[claim_id].status

    def approve(self, claim_id: str) -> None:
        self.claims[claim_id].status = ClaimStatus.APPROVED

    def reject(self, claim_id: str) -> None:
        self.claims[claim_id].status = ClaimStatus.REJECTED


# ---------------------------------------------------------------- availability
class AvailabilityPort(Protocol):
    def office_on(self, volunteer_id: str, day: date) -> Optional[str]:
        """Office the volunteer is physically at that day, or None (home, holiday, unknown)."""
        ...


class FakeAvailability:
    """Stand-in for desk booking / calendar / 'I'm in today' chat check-ins."""

    def __init__(self) -> None:
        self._where: dict[tuple[str, date], str] = {}

    def set(self, volunteer_id: str, day: date, office_id: Optional[str]) -> None:
        if office_id is None:
            self._where.pop((volunteer_id, day), None)
        else:
            self._where[(volunteer_id, day)] = office_id

    def office_on(self, volunteer_id: str, day: date) -> Optional[str]:
        return self._where.get((volunteer_id, day))
