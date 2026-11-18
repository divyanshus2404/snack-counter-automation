r"""The refill lifecycle.

    empty reported --> SEEKING_BUYER --accept--> COMMITTED --receipt--> PURCHASED --HR--> CLAIM_SUBMITTED --> REIMBURSED
          |               ^   |  decline/timeout: offer next person     |  over cap                    \--> CLAIM_REJECTED
          |               |   |  nobody left: broadcast to office        v
          |               |   |                                      NEEDS_REVIEW --coordinator ok--> PURCHASED
          |               \---+---- buy deadline missed: release buyer, offer next person
          v
    WAITING_FOR_BUDGET (month's budget used) --new month--> SEEKING_BUYER

All state changes happen under one lock, so "check state, then change it" is atomic.
In production that lock is a conditional UPDATE (... WHERE state='seeking_buyer') on the refill row.
`tick()` is the scheduler: run it every few minutes to handle timeouts, HR retries and HR status sync.
"""
from __future__ import annotations

import itertools
import threading
from typing import Iterable, Optional

from . import budget
from .models import Office, Purchase, Refill, RefillState, Timeouts, Volunteer
from .money import CurrencyMismatch, Money
from .ports import AvailabilityPort, ChatPort, ClaimStatus, Clock, HRPort, HRUnavailable
from .selection import rank_candidates


class RefillError(Exception):
    pass


class AlreadyTaken(RefillError):
    """Someone else has already committed to this refill."""


class NotOfferedToYou(RefillError):
    pass


class NotYourRefill(RefillError):
    pass


class InvalidState(RefillError):
    pass


class SnackCounterService:
    def __init__(
        self,
        offices: Iterable[Office],
        volunteers: Iterable[Volunteer],
        chat: ChatPort,
        hr: HRPort,
        availability: AvailabilityPort,
        clock: Clock,
        timeouts: Timeouts = Timeouts(),
    ):
        self.offices = {o.id: o for o in offices}
        self.volunteers = {v.id: v for v in volunteers}
        self.chat = chat
        self.hr = hr
        self.availability = availability
        self.clock = clock
        self.timeouts = timeouts
        self.refills: dict[str, Refill] = {}
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    # ------------------------------------------------------------ queries
    def active_refill(self, office_id: str) -> Optional[Refill]:
        return next((r for r in self.refills.values() if r.office_id == office_id and r.is_active), None)

    def get(self, refill_id: str) -> Refill:
        try:
            return self.refills[refill_id]
        except KeyError:
            raise RefillError(f"unknown refill {refill_id}") from None

    # ------------------------------------------------------------ commands
    def report_empty(self, office_id: str, reporter_id: str) -> Refill:
        """Anyone presses 'box is empty'. Duplicate reports join the refill already in progress."""
        with self._lock:
            now = self.clock.now()
            office = self.offices[office_id]
            existing = self.active_refill(office_id)
            if existing:
                existing.log(now, f"duplicate empty report from {reporter_id}")
                return existing

            refill = Refill(
                id=f"R{next(self._ids)}",
                office_id=office_id,
                reported_by=reporter_id,
                reported_at=now,
                state=RefillState.SEEKING_BUYER,
            )
            refill.log(now, f"reported empty by {reporter_id}")
            self.refills[refill.id] = refill
            self._start_search(refill)
            return refill

    def accept(self, refill_id: str, volunteer_id: str) -> Refill:
        """'I'll buy it.' Exactly one caller can win; everyone else gets AlreadyTaken."""
        with self._lock:
            now = self.clock.now()
            r = self.get(refill_id)
            if volunteer_id not in self.volunteers:
                raise RefillError(f"{volunteer_id} is not a volunteer")
            if r.state != RefillState.SEEKING_BUYER:
                if r.buyer_id:
                    raise AlreadyTaken(f"{r.id} already taken by {r.buyer_id}")
                raise InvalidState(f"{r.id} is {r.state.value}")
            if not r.broadcast and r.offered_to != volunteer_id:
                raise NotOfferedToYou(f"{r.id} is currently offered to {r.offered_to}")

            r.state = RefillState.COMMITTED
            r.buyer_id = volunteer_id
            r.buy_deadline = now + self.timeouts.buy_deadline
            r.offered_to = None
            r.offer_expires_at = None
            r.broadcast = False
            r.log(now, f"committed by {volunteer_id}")

            office = self.offices[r.office_id]
            buyer = self.volunteers[volunteer_id]
            self.chat.send_direct(
                buyer.chat_id,
                f"Thanks! Refill {r.id} for {office.name} is yours. Spend up to {r.spend_cap} "
                f"and upload the receipt by {r.buy_deadline.astimezone(office.tz):%a %d %b %H:%M} ({office.name} time).",
            )
            self.chat.post_channel(office.chat_channel, f"{buyer.name} is buying snacks for {office.name}. No one else needs to.")
            return r

    def decline(self, refill_id: str, volunteer_id: str) -> Refill:
        with self._lock:
            now = self.clock.now()
            r = self.get(refill_id)
            if r.state != RefillState.SEEKING_BUYER or r.offered_to != volunteer_id:
                raise NotOfferedToYou(f"{r.id} is not offered to {volunteer_id}")
            r.passed_over.add(volunteer_id)
            r.log(now, f"declined by {volunteer_id}")
            self._offer_next(r)
            return r

    def record_purchase(
        self,
        refill_id: str,
        volunteer_id: str,
        amount: Money,
        receipt_image: bytes,
        items: list[str] | None = None,
    ) -> Refill:
        """Buyer uploads the receipt. Within the cap it goes straight to HR."""
        with self._lock:
            now = self.clock.now()
            r = self.get(refill_id)
            if r.state != RefillState.COMMITTED:
                raise InvalidState(f"{r.id} is {r.state.value}, not committed")
            if r.buyer_id != volunteer_id:
                raise NotYourRefill(f"{r.id} belongs to {r.buyer_id}")
            office = self.offices[r.office_id]
            if amount.currency != office.currency:
                raise CurrencyMismatch(f"{office.name} receipts must be in {office.currency}")
            if amount.amount <= 0:
                raise ValueError("amount must be positive")
            if not receipt_image:
                raise ValueError("a receipt image is required")

            r.purchase = Purchase(amount, receipt_image, list(items or []), now)
            r.log(now, f"purchased {amount}")
            if r.spend_cap is not None and amount > r.spend_cap:
                r.state = RefillState.NEEDS_REVIEW
                self.chat.send_direct(
                    office.admin_chat_id,
                    f"Refill {r.id}: receipt {amount} is over the {r.spend_cap} cap. Approve to send it to HR.",
                )
                self.chat.send_direct(
                    self.volunteers[volunteer_id].chat_id,
                    f"Your receipt is over the cap; the {office.name} coordinator will review it.",
                )
            else:
                r.state = RefillState.PURCHASED
                self._submit_claim(r)
            return r

    def approve_over_cap(self, refill_id: str, approver_chat_id: str) -> Refill:
        with self._lock:
            now = self.clock.now()
            r = self.get(refill_id)
            office = self.offices[r.office_id]
            if approver_chat_id != office.admin_chat_id:
                raise RefillError("only the office coordinator can approve")
            if r.state != RefillState.NEEDS_REVIEW:
                raise InvalidState(f"{r.id} is {r.state.value}")
            r.state = RefillState.PURCHASED
            r.log(now, f"over-cap receipt approved by {approver_chat_id}")
            self._submit_claim(r)
            return r

    # ------------------------------------------------------------ scheduler
    def tick(self) -> None:
        """Run periodically. Handles every time-based rule."""
        with self._lock:
            now = self.clock.now()
            for r in list(self.refills.values()):
                office = self.offices[r.office_id]
                if r.state == RefillState.WAITING_FOR_BUDGET:
                    if budget.cap_for_new_refill(office, self.refills.values(), now, r.id):
                        r.log(now, "budget available again")
                        self._start_search(r)

                elif r.state == RefillState.SEEKING_BUYER and r.offer_expires_at and now >= r.offer_expires_at:
                    if r.broadcast:
                        if not r.broadcast_escalated:
                            r.broadcast_escalated = True
                            r.log(now, "nobody took the broadcast; escalated to coordinator")
                            self.chat.send_direct(
                                office.admin_chat_id,
                                f"Nobody has picked up refill {r.id} for {office.name}. Please arrange it.",
                            )
                    else:
                        who = r.offered_to
                        r.passed_over.add(who)
                        r.log(now, f"offer to {who} expired")
                        self.chat.send_direct(self.volunteers[who].chat_id, f"No worries, refill {r.id} has been passed on.")
                        self._offer_next(r)

                elif r.state == RefillState.COMMITTED and r.buy_deadline and now >= r.buy_deadline:
                    who = r.buyer_id
                    r.passed_over.add(who)
                    r.buyer_id = None
                    r.buy_deadline = None
                    r.state = RefillState.SEEKING_BUYER
                    r.log(now, f"{who} missed the buy deadline; released")
                    self.chat.send_direct(
                        self.volunteers[who].chat_id,
                        f"Refill {r.id} was not completed in time, so it has been handed to someone else. "
                        f"Please don't buy for it now.",
                    )
                    self._offer_next(r)

                elif r.state == RefillState.PURCHASED:
                    self._submit_claim(r)  # retry after an HR outage

                elif r.state == RefillState.CLAIM_SUBMITTED:
                    self._sync_claim(r, office)

    # ------------------------------------------------------------ internals
    def _start_search(self, r: Refill) -> None:
        now = self.clock.now()
        office = self.offices[r.office_id]
        cap = budget.cap_for_new_refill(office, self.refills.values(), now, r.id)
        if cap is None:
            r.state = RefillState.WAITING_FOR_BUDGET
            r.spend_cap = None
            r.log(now, "budget exhausted for this month")
            left = budget.remaining(office, self.refills.values(), now, r.id)
            self.chat.post_channel(
                office.chat_channel,
                f"The {office.name} snack box is empty, but this month's budget is used up "
                f"({left} left). It will be refilled at the start of next month.",
            )
            self.chat.send_direct(office.admin_chat_id, f"{office.name} snack budget exhausted; refill {r.id} is on hold.")
            return
        r.state = RefillState.SEEKING_BUYER
        r.spend_cap = cap
        self._offer_next(r)

    def _offer_next(self, r: Refill) -> None:
        now = self.clock.now()
        office = self.offices[r.office_id]
        candidates = rank_candidates(
            office_id=r.office_id,
            day=office.local_date(now),
            volunteers=self.volunteers.values(),
            availability=self.availability,
            refills=[x for x in self.refills.values() if x.id != r.id],
            since=now - self.timeouts.lookback_for_fairness,
            exclude=r.passed_over,
        )
        if candidates:
            v = candidates[0]
            r.offered_to = v.id
            r.broadcast = False
            r.offer_expires_at = now + self.timeouts.offer_response
            r.log(now, f"offered to {v.id}")
            self.chat.send_direct(
                v.chat_id,
                f"The {office.name} snack box is empty and it's your turn (you're in the office today). "
                f"Can you buy up to {r.spend_cap}? [I'll buy] [Can't today] - offer expires in "
                f"{int(self.timeouts.offer_response.total_seconds() // 3600)}h.",
            )
        else:
            r.offered_to = None
            r.broadcast = True
            r.broadcast_escalated = False
            r.offer_expires_at = now + self.timeouts.broadcast_escalation
            r.log(now, "no eligible volunteer; broadcast to office")
            self.chat.post_channel(
                office.chat_channel,
                f"The {office.name} snack box is empty. First volunteer to tap [I'll buy] gets refill {r.id} "
                f"(budget up to {r.spend_cap}).",
            )

    def _submit_claim(self, r: Refill) -> None:
        now = self.clock.now()
        office = self.offices[r.office_id]
        buyer = self.volunteers[r.buyer_id]
        p = r.purchase
        try:
            claim_id = self.hr.submit_claim(
                employee_id=buyer.employee_id,
                amount=p.amount.amount,
                currency=p.amount.currency,
                description=f"Snack counter refill {r.id}, {office.name}, {office.local_date(p.purchased_at).isoformat()}",
                receipt_image=p.receipt_image,
                idempotency_key=f"snack-refill-{r.id}",
            )
        except HRUnavailable as e:
            r.log(now, f"HR submit failed ({e}); will retry")
            return
        r.claim_id = claim_id
        r.claim_submitted_at = now
        r.state = RefillState.CLAIM_SUBMITTED
        r.log(now, f"claim {claim_id} submitted to HR")
        self.chat.send_direct(buyer.chat_id, f"Your claim {claim_id} for {p.amount} has been sent to HR. Nothing else to do.")

    def _sync_claim(self, r: Refill, office: Office) -> None:
        now = self.clock.now()
        try:
            status = self.hr.claim_status(r.claim_id)
        except HRUnavailable:
            return
        buyer = self.volunteers[r.buyer_id]
        if status == ClaimStatus.APPROVED:
            r.state = RefillState.REIMBURSED
            r.resolved_at = now
            r.log(now, "HR approved; reimbursed")
            self.chat.send_direct(buyer.chat_id, f"HR approved claim {r.claim_id}. Thanks for refilling!")
        elif status == ClaimStatus.REJECTED:
            r.state = RefillState.CLAIM_REJECTED
            r.resolved_at = now
            r.log(now, "HR rejected claim")
            self.chat.send_direct(buyer.chat_id, f"HR rejected claim {r.claim_id}. The {office.name} coordinator will follow up.")
            self.chat.send_direct(office.admin_chat_id, f"HR rejected claim {r.claim_id} (refill {r.id}, {buyer.name}).")
        elif not r.claim_nudged and now - r.claim_submitted_at >= self.timeouts.claim_nudge_after:
            r.claim_nudged = True
            r.log(now, "claim pending too long; coordinator nudged")
            self.chat.send_direct(
                office.admin_chat_id,
                f"Claim {r.claim_id} for {buyer.name} has been pending with HR for "
                f"{(now - r.claim_submitted_at).days} days.",
            )
