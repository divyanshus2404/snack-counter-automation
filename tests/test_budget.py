"""Budget check: per office, in its own currency, per local calendar month."""
import unittest
from datetime import datetime, timedelta, timezone

from snack import CurrencyMismatch, Money, RefillError, RefillState

from .helpers import RECEIPT, World


class BudgetTest(unittest.TestCase):
    def test_cap_is_typical_max_while_budget_allows(self):
        w = World()
        self.assertEqual(w.svc.report_empty("oslo", "o1").spend_cap, Money(1200, "NOK"))
        self.assertEqual(w.svc.report_empty("blr", "b1").spend_cap, Money(3000, "INR"))

    def test_cap_shrinks_to_what_is_left(self):
        w = World()
        for _ in range(4):
            w.full_refill("oslo", Money(1200, "NOK"))
        w.full_refill("oslo", Money(500, "NOK"))  # 5300 spent, 700 left
        r = w.svc.report_empty("oslo", "o1")
        self.assertEqual(r.spend_cap, Money(700, "NOK"))

    def test_exhausted_budget_puts_refill_on_hold_until_next_month(self):
        w = World()
        for _ in range(5):
            w.full_refill("oslo", Money(1200, "NOK"))  # exactly 6000 NOK
        r = w.svc.report_empty("oslo", "o1")
        self.assertEqual(r.state, RefillState.WAITING_FOR_BUDGET)
        self.assertIsNone(r.offered_to)
        self.assertTrue(any("budget exhausted" in m for m in w.chat.to("@oslo-coordinator")))

        w.svc.tick()
        self.assertEqual(r.state, RefillState.WAITING_FOR_BUDGET)

        w.clock.set(datetime(2026, 11, 30, 23, 30, tzinfo=timezone.utc))  # 00:30 on 1 Dec in Oslo
        w.svc.tick()
        self.assertEqual(r.state, RefillState.SEEKING_BUYER)
        self.assertEqual(r.spend_cap, Money(1200, "NOK"))

    def test_open_refill_reserves_budget(self):
        # 4 refills spent = 4800 NOK. An open refill reserving 1200 leaves 0 for a refill elsewhere
        # in the same office - the reservation stops two in-flight refills overspending together.
        w = World()
        for _ in range(4):
            w.full_refill("oslo", Money(1200, "NOK"))
        open_refill = w.svc.report_empty("oslo", "o1")
        self.assertEqual(open_refill.spend_cap, Money(1200, "NOK"))
        from snack import budget
        office = w.svc.offices["oslo"]
        self.assertEqual(budget.remaining(office, w.svc.refills.values(), w.clock.now()), Money(0, "NOK"))

    def test_budgets_are_separate_per_office(self):
        w = World()
        for _ in range(5):
            w.full_refill("oslo", Money(1200, "NOK"))
        r = w.svc.report_empty("blr", "b1")
        self.assertEqual(r.state, RefillState.SEEKING_BUYER)
        self.assertEqual(r.spend_cap, Money(3000, "INR"))

    def test_over_cap_receipt_needs_coordinator_before_hr(self):
        w = World()
        r = w.svc.report_empty("oslo", "o1")
        w.svc.accept(r.id, "o1")
        w.svc.record_purchase(r.id, "o1", Money(1350, "NOK"), RECEIPT)
        self.assertEqual(r.state, RefillState.NEEDS_REVIEW)
        self.assertEqual(w.hr.claims, {})

        with self.assertRaises(RefillError):
            w.svc.approve_over_cap(r.id, "@o2")  # not the coordinator
        w.svc.approve_over_cap(r.id, "@oslo-coordinator")
        self.assertEqual(r.state, RefillState.CLAIM_SUBMITTED)

    def test_receipt_in_wrong_currency_is_rejected(self):
        w = World()
        r = w.svc.report_empty("oslo", "o1")
        w.svc.accept(r.id, "o1")
        with self.assertRaises(CurrencyMismatch):
            w.svc.record_purchase(r.id, "o1", Money(800, "INR"), RECEIPT)

    def test_month_follows_office_local_time(self):
        # 30 Nov 19:00 UTC is already 1 Dec 00:30 in Bengaluru.
        w = World(start=datetime(2026, 11, 30, 18, 0, tzinfo=timezone.utc))
        r = w.svc.report_empty("blr", "b1")
        w.svc.accept(r.id, r.offered_to)
        w.clock.set(datetime(2026, 11, 30, 19, 0, tzinfo=timezone.utc))
        w.svc.record_purchase(r.id, r.buyer_id, Money(2000, "INR"), RECEIPT)

        from snack import budget
        office = w.svc.offices["blr"]
        self.assertEqual(budget.spent_in_month(office, w.svc.refills.values(), 2026, 11), Money(0, "INR"))
        self.assertEqual(budget.spent_in_month(office, w.svc.refills.values(), 2026, 12), Money(2000, "INR"))

    def test_visitor_purchase_charges_the_office_they_bought_for(self):
        # An Oslo employee (paid in NOK) refills the Bengaluru box during a visit.
        w = World(present={"blr": ["o2"]})
        r = w.svc.report_empty("blr", "b1")
        self.assertEqual(r.offered_to, "o2")
        w.svc.accept(r.id, "o2")
        w.svc.record_purchase(r.id, "o2", Money(1800, "INR"), RECEIPT)

        claim = w.hr.claims[r.claim_id]
        self.assertEqual((claim.employee_id, claim.currency), ("EMP-O2", "INR"))  # HR converts to NOK payroll
        from snack import budget
        blr, oslo = w.svc.offices["blr"], w.svc.offices["oslo"]
        self.assertEqual(budget.spent_in_month(blr, w.svc.refills.values(), 2026, 11), Money(1800, "INR"))
        self.assertEqual(budget.spent_in_month(oslo, w.svc.refills.values(), 2026, 11), Money(0, "NOK"))


if __name__ == "__main__":
    unittest.main()
