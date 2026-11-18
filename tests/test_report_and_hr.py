"""Totals across currencies, and the HR integration rules."""
import unittest
from datetime import timedelta
from decimal import Decimal

from snack import CurrencyMismatch, Money, RefillState, monthly_report

from .helpers import RECEIPT, World

RATES_EUR = {"NOK": Decimal("0.085"), "INR": Decimal("0.0105")}


class MoneyTest(unittest.TestCase):
    def test_cannot_add_different_currencies(self):
        with self.assertRaises(CurrencyMismatch):
            Money(100, "NOK") + Money(100, "INR")

    def test_cannot_compare_different_currencies(self):
        with self.assertRaises(CurrencyMismatch):
            Money(100, "NOK") < Money(100, "INR")

    def test_amounts_are_exact(self):
        self.assertEqual(Money("0.10", "NOK") + Money("0.20", "NOK"), Money("0.30", "NOK"))


class MonthlyReportTest(unittest.TestCase):
    def _world_with_spend(self):
        w = World()
        w.full_refill("oslo", Money(1000, "NOK"), ["Chips", "fruit"])
        w.full_refill("oslo", Money(500, "NOK"), ["chips"])
        w.full_refill("blr", Money(2000, "INR"), ["samosa"])
        w.full_refill("blr", Money(3000, "INR"), ["biscuits", "samosa"])
        return w

    def _report(self, w, currency="EUR", rates=RATES_EUR):
        return monthly_report(w.svc.offices.values(), w.svc.volunteers, w.svc.refills.values(), 2026, 11, currency, rates)

    def test_totals_per_office_and_converted_total(self):
        rep = self._report(self._world_with_spend())
        oslo, blr = rep.offices
        self.assertEqual(oslo.spent, Money(1500, "NOK"))
        self.assertEqual(oslo.remaining, Money(4500, "NOK"))
        self.assertEqual(blr.spent, Money(5000, "INR"))
        self.assertEqual(blr.remaining, Money(10000, "INR"))
        # 1500 * 0.085 = 127.50 EUR ; 5000 * 0.0105 = 52.50 EUR
        self.assertEqual(rep.total, Money("180.00", "EUR"))

    def test_total_in_one_office_currency(self):
        rep = self._report(self._world_with_spend(), "NOK", {"INR": Decimal("0.125")})
        self.assertEqual(rep.total, Money(1500 + 625, "NOK"))

    def test_missing_rate_is_an_error_not_a_silent_zero(self):
        with self.assertRaises(KeyError):
            self._report(self._world_with_spend(), "EUR", {"NOK": Decimal("0.085")})

    def test_rejected_claims_are_not_counted_as_spend(self):
        w = World()
        r = w.full_refill("oslo", Money(900, "NOK"), approve=False)
        w.hr.reject(r.claim_id)
        w.svc.tick()
        self.assertEqual(r.state, RefillState.CLAIM_REJECTED)
        self.assertEqual(self._report(w).offices[0].spent, Money(0, "NOK"))

    def test_pending_claims_count_as_spend(self):
        w = World()
        w.full_refill("oslo", Money(900, "NOK"), approve=False)
        oslo = self._report(w).offices[0]
        self.assertEqual(oslo.spent, Money(900, "NOK"))
        self.assertEqual(oslo.claims_still_open, 1)

    def test_report_shows_what_gets_bought(self):
        oslo = self._report(self._world_with_spend()).offices[0]
        self.assertEqual(oslo.top_items[0], ("chips", 2))

    def test_render_mentions_rates(self):
        text = self._report(self._world_with_spend()).render()
        self.assertIn("TOTAL: 180.00 EUR", text)
        self.assertIn("1 NOK = 0.085 EUR", text)


class HRIntegrationTest(unittest.TestCase):
    def _bought(self, w):
        r = w.svc.report_empty("oslo", "o3")
        w.svc.accept(r.id, r.offered_to)
        return r

    def test_hr_outage_is_retried_without_duplicate_claims(self):
        w = World()
        r = self._bought(w)
        w.hr.fail_next_submits = 2
        w.svc.record_purchase(r.id, r.buyer_id, Money(700, "NOK"), RECEIPT)
        self.assertEqual(r.state, RefillState.PURCHASED)
        w.svc.tick()  # still failing
        self.assertEqual(r.state, RefillState.PURCHASED)
        w.svc.tick()  # HR back
        self.assertEqual(r.state, RefillState.CLAIM_SUBMITTED)
        w.svc.tick()
        self.assertEqual(len(w.hr.claims), 1)

    def test_idempotency_key_prevents_double_claim(self):
        w = World()
        r = self._bought(w)
        w.svc.record_purchase(r.id, r.buyer_id, Money(700, "NOK"), RECEIPT)
        again = w.hr.submit_claim("EMP-O1", Decimal(700), "NOK", "x", RECEIPT, f"snack-refill-{r.id}")
        self.assertEqual(again, r.claim_id)
        self.assertEqual(len(w.hr.claims), 1)

    def test_slow_claim_nudges_coordinator_once(self):
        w = World()
        r = self._bought(w)
        w.svc.record_purchase(r.id, r.buyer_id, Money(700, "NOK"), RECEIPT)
        w.clock.advance(timedelta(days=6))
        w.svc.tick()
        self.assertFalse(any("pending with HR" in m for m in w.chat.to("@oslo-coordinator")))
        w.clock.advance(timedelta(days=1))
        w.svc.tick()
        w.clock.advance(timedelta(days=1))
        w.svc.tick()
        nudges = [m for m in w.chat.to("@oslo-coordinator") if "pending with HR" in m]
        self.assertEqual(len(nudges), 1)

    def test_rejection_notifies_buyer_and_coordinator(self):
        w = World()
        r = self._bought(w)
        w.svc.record_purchase(r.id, r.buyer_id, Money(700, "NOK"), RECEIPT)
        w.hr.reject(r.claim_id)
        w.svc.tick()
        self.assertTrue(any("rejected" in m for m in w.chat.to("@o1")))
        self.assertTrue(any("rejected" in m for m in w.chat.to("@oslo-coordinator")))


if __name__ == "__main__":
    unittest.main()
