from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from snack import Money, SnackCounterService, Volunteer, default_offices
from snack.ports import FakeAvailability, FakeChat, FakeClock, FakeHR

# Monday 16 Nov 2026, 08:00 UTC = 09:00 Oslo = 13:30 Bengaluru
START = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
RECEIPT = b"\x89PNG fake receipt"


def volunteers() -> list[Volunteer]:
    vs = []
    for i in range(1, 5):
        vs.append(Volunteer(f"o{i}", f"Oslo {i}", f"EMP-O{i}", f"@o{i}", "oslo", "NOK"))
        vs.append(Volunteer(f"b{i}", f"Blr {i}", f"EMP-B{i}", f"@b{i}", "blr", "INR"))
    return vs


class World:
    """A fully wired service with fake chat, HR, clock and availability."""

    def __init__(self, start: datetime = START, present: dict[str, list[str]] | None = None, days: int = 60):
        self.clock = FakeClock(start)
        self.chat = FakeChat()
        self.hr = FakeHR()
        self.availability = FakeAvailability()
        self.svc = SnackCounterService(
            default_offices(), volunteers(), self.chat, self.hr, self.availability, self.clock
        )
        if present is None:  # by default everyone is at their home office every day
            present = {"oslo": ["o1", "o2", "o3", "o4"], "blr": ["b1", "b2", "b3", "b4"]}
        for office_id, ids in present.items():
            self.at_office(office_id, ids, days)

    def at_office(self, office_id: str, ids: list[str], days: int = 60, start: date | None = None) -> None:
        first = start or self.clock.now().date() - timedelta(days=1)
        for vid in ids:
            for d in range(days):
                self.availability.set(vid, first + timedelta(days=d), office_id)

    def away(self, vid: str, days: int = 60) -> None:
        first = self.clock.now().date() - timedelta(days=1)
        for d in range(days):
            self.availability.set(vid, first + timedelta(days=d), None)

    def full_refill(self, office_id: str, amount: Money, items=None, approve: bool = True):
        """Drive one refill from empty to reimbursed (or claim submitted)."""
        r = self.svc.report_empty(office_id, "someone")
        buyer = r.offered_to
        self.svc.accept(r.id, buyer)
        self.svc.record_purchase(r.id, buyer, amount, RECEIPT, items or [])
        if approve and r.claim_id:
            self.hr.approve(r.claim_id)
            self.svc.tick()
        return r
