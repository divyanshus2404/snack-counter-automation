"""The snack counter rules.

    box empty -> LOOKING_FOR_BUYER -> BUYER_COMMITTED -> CLAIM_SENT -> REIMBURSED
                   ^      |                |
                   |      | no answer      | didn't buy in time
                   |      v                |
                   +-- ask next person <---+

Rules:
  * Only one open refill per office.
  * Ask one person at a time: someone in the office today who has done the fewest refills.
  * They have 2 hours to answer. Once they accept, they have 24 hours to buy.
  * If nobody is left to ask, post in the office channel: first to accept gets it.
  * Spending cap = the lower of the max purchase and the budget left this month.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from .models import CurrencyMismatch, Money, Office, Refill, State, Volunteer

ANSWER_TIME = timedelta(hours=2)
BUY_TIME = timedelta(hours=24)


class RefillError(Exception):
    pass


class SnackCounter:
    def __init__(self, offices: list[Office], volunteers: list[Volunteer], chat, hr, clock):
        self.offices = {o.id: o for o in offices}
        self.volunteers = {v.id: v for v in volunteers}
        self.chat = chat
        self.hr = hr
        self.clock = clock
        self.refills: dict[str, Refill] = {}
        self.in_office: dict[str, set[str]] = {o.id: set() for o in offices}  # who is at each office today
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- attendance
    def set_in_office(self, office_id: str, volunteer_ids: list[str]):
        """Today's attendance, e.g. from a morning 'I'm in' check-in. Visitors count."""
        self.in_office[office_id] = set(volunteer_ids)

    # ---------------------------------------------------------------- the lifecycle
    def report_empty(self, office_id: str) -> Optional[Refill]:
        with self._lock:
            open_refill = self._open_refill(office_id)
            if open_refill:
                return open_refill  # someone already reported it: no second refill

            office = self.offices[office_id]
            left = self.budget_left(office_id)
            if not left > Money(0, office.currency):
                self.chat.send(office.channel, f"The box is empty but this month's {office.name} budget is used up.")
                return None

            cap = office.max_purchase if office.max_purchase < left else left
            refill = Refill(id=f"R{len(self.refills) + 1}", office_id=office_id, state=State.LOOKING_FOR_BUYER, cap=cap)
            self.refills[refill.id] = refill
            self._ask_next_person(refill)
            return refill

    def accept(self, refill_id: str, volunteer_id: str) -> Refill:
        with self._lock:  # check and update together, so only one person can ever win
            refill = self.refills[refill_id]
            if refill.state != State.LOOKING_FOR_BUYER:
                raise RefillError("Someone else is already buying.")
            if not refill.open_to_all and refill.asked != volunteer_id:
                raise RefillError("This refill was not offered to you.")

            refill.state = State.BUYER_COMMITTED
            refill.buyer = volunteer_id
            refill.buy_by = self.clock.now + BUY_TIME
            refill.asked = None
            office = self.offices[refill.office_id]
            self.chat.send(volunteer_id, f"Thanks! Spend up to {refill.cap} and upload the receipt within 24 hours.")
            self.chat.send(office.channel, f"{self.volunteers[volunteer_id].name} is buying snacks. No one else needs to.")
            return refill

    def decline(self, refill_id: str, volunteer_id: str):
        with self._lock:
            refill = self.refills[refill_id]
            if refill.asked != volunteer_id:
                raise RefillError("This refill was not offered to you.")
            refill.skipped.add(volunteer_id)
            self._ask_next_person(refill)

    def record_purchase(self, refill_id: str, volunteer_id: str, amount: Money, receipt: bytes) -> Refill:
        with self._lock:
            refill = self.refills[refill_id]
            office = self.offices[refill.office_id]
            if refill.state != State.BUYER_COMMITTED or refill.buyer != volunteer_id:
                raise RefillError("This refill is not yours to buy.")
            if amount.currency != office.currency:
                raise CurrencyMismatch(f"{office.name} receipts must be in {office.currency}.")
            if amount > refill.cap:
                raise RefillError(f"Over the {refill.cap} limit.")
            if not receipt:
                raise RefillError("A receipt photo is required.")

            refill.amount = amount
            refill.bought_at = self.clock.now
            refill.claim_id = self.hr.submit_claim(
                employee_id=self.volunteers[volunteer_id].employee_id,
                amount=amount.amount,
                currency=amount.currency,
                description=f"Snack refill {refill.id}, {office.name}",
                receipt=receipt,
            )
            refill.state = State.CLAIM_SENT
            self.chat.send(volunteer_id, f"Your claim for {amount} has been sent to HR.")
            return refill

    # ---------------------------------------------------------------- run every few minutes
    def check_timeouts(self):
        with self._lock:
            now = self.clock.now
            for refill in self.refills.values():
                if refill.state == State.LOOKING_FOR_BUYER and refill.asked and now >= refill.answer_by:
                    refill.skipped.add(refill.asked)
                    self._ask_next_person(refill)

                elif refill.state == State.BUYER_COMMITTED and now >= refill.buy_by:
                    self.chat.send(refill.buyer, "You didn't buy in time, so the refill has been handed on. Please don't buy now.")
                    refill.skipped.add(refill.buyer)
                    refill.buyer = None
                    refill.state = State.LOOKING_FOR_BUYER
                    self._ask_next_person(refill)

    def check_hr(self):
        with self._lock:
            for refill in self.refills.values():
                if refill.state == State.CLAIM_SENT and self.hr.status(refill.claim_id) == "approved":
                    refill.state = State.REIMBURSED
                    self.chat.send(refill.buyer, "HR approved your claim. Thanks for refilling!")

    # ---------------------------------------------------------------- choosing who buys
    def _ask_next_person(self, refill: Refill):
        office = self.offices[refill.office_id]
        person = self._pick_buyer(refill)
        if person:
            refill.asked = person
            refill.answer_by = self.clock.now + ANSWER_TIME
            self.chat.send(person, f"The {office.name} snack box is empty. Can you buy up to {refill.cap}? Reply within 2 hours.")
        else:
            refill.asked = None
            refill.open_to_all = True
            self.chat.send(office.channel, f"The {office.name} snack box is empty. First volunteer to accept gets it.")

    def _pick_buyer(self, refill: Refill) -> Optional[str]:
        busy = {r.asked for r in self.refills.values()} | {
            r.buyer for r in self.refills.values() if r.state == State.BUYER_COMMITTED
        }
        candidates = [
            v for v in self.in_office[refill.office_id]
            if v in self.volunteers and v not in refill.skipped and v not in busy
        ]
        if not candidates:
            return None
        # Fairness: fewest refills bought so far goes first; name breaks ties so the choice is predictable.
        return min(candidates, key=lambda v: (self._refills_bought_by(v), v))

    def _refills_bought_by(self, volunteer_id: str) -> int:
        return sum(1 for r in self.refills.values() if r.buyer == volunteer_id and r.amount)

    def _open_refill(self, office_id: str) -> Optional[Refill]:
        for r in self.refills.values():
            if r.office_id == office_id and r.state in (State.LOOKING_FOR_BUYER, State.BUYER_COMMITTED):
                return r
        return None

    # ---------------------------------------------------------------- budget and report
    def spent(self, office_id: str, year: int, month: int) -> Money:
        office = self.offices[office_id]
        total = Money(0, office.currency)
        for r in self.refills.values():
            if r.office_id == office_id and r.amount and (r.bought_at.year, r.bought_at.month) == (year, month):
                total = total + r.amount
        return total

    def budget_left(self, office_id: str) -> Money:
        now = self.clock.now
        return self.offices[office_id].monthly_budget - self.spent(office_id, now.year, now.month)

    def monthly_report(self, year: int, month: int, currency: str, rates: dict[str, Decimal]) -> dict[str, Money]:
        """Each office in its own currency, plus one total converted at the given rates."""
        report = {}
        total = Money(0, currency)
        for office in self.offices.values():
            spent = self.spent(office.id, year, month)
            report[office.name] = spent
            total = total + spent.convert(currency, rates[office.currency])
        report["Total"] = total
        return report
