"""Rule: budgets and totals are correct across both currencies."""
import unittest
from datetime import datetime
from decimal import Decimal

from snack import CurrencyMismatch, Money, RefillError

from .common import RECEIPT, complete_refill, make_counter

RATES_TO_EUR = {"NOK": Decimal("0.085"), "INR": Decimal("0.0105")}


class BudgetTest(unittest.TestCase):
    def test_spending_cap_is_the_typical_maximum(self):
        counter = make_counter()
        self.assertEqual(counter.report_empty("oslo").cap, Money(1200, "NOK"))
        self.assertEqual(counter.report_empty("blr").cap, Money(3000, "INR"))

    def test_cap_shrinks_to_what_is_left_this_month(self):
        counter = make_counter()
        for _ in range(4):
            complete_refill(counter, "oslo", Money(1200, "NOK"))
        complete_refill(counter, "oslo", Money(500, "NOK"))  # 5,300 of 6,000 spent
        self.assertEqual(counter.report_empty("oslo").cap, Money(700, "NOK"))

    def test_no_refill_when_the_budget_is_used_up(self):
        counter = make_counter()
        for _ in range(5):
            complete_refill(counter, "oslo", Money(1200, "NOK"))  # exactly 6,000
        self.assertIsNone(counter.report_empty("oslo"))
        self.assertIn("budget is used up", counter.chat.to("#snacks-oslo")[-1])

    def test_budget_resets_next_month(self):
        counter = make_counter()
        for _ in range(5):
            complete_refill(counter, "oslo", Money(1200, "NOK"))
        counter.clock.now = datetime(2026, 12, 1, 9, 0)
        self.assertEqual(counter.report_empty("oslo").cap, Money(1200, "NOK"))

    def test_offices_have_separate_budgets(self):
        counter = make_counter()
        for _ in range(5):
            complete_refill(counter, "oslo", Money(1200, "NOK"))
        self.assertEqual(counter.budget_left("blr"), Money(15000, "INR"))

    def test_receipt_over_the_cap_is_refused(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        counter.accept(refill.id, "o1")
        with self.assertRaises(RefillError):
            counter.record_purchase(refill.id, "o1", Money(1300, "NOK"), RECEIPT)

    def test_receipt_in_the_wrong_currency_is_refused(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        counter.accept(refill.id, "o1")
        with self.assertRaises(CurrencyMismatch):
            counter.record_purchase(refill.id, "o1", Money(800, "INR"), RECEIPT)

    def test_visitor_spend_counts_for_the_office_they_bought_for(self):
        counter = make_counter()
        counter.set_in_office("blr", ["o2"])  # Oslo employee visiting Bengaluru
        refill = complete_refill(counter, "blr", Money(1800, "INR"))
        self.assertEqual(counter.hr.claims[refill.claim_id]["currency"], "INR")  # HR converts to NOK payroll
        self.assertEqual(counter.budget_left("blr"), Money(13200, "INR"))
        self.assertEqual(counter.budget_left("oslo"), Money(6000, "NOK"))

    def test_nok_and_inr_can_never_be_added_directly(self):
        with self.assertRaises(CurrencyMismatch):
            Money(100, "NOK") + Money(100, "INR")

    def test_monthly_report_totals_across_currencies(self):
        counter = make_counter()
        complete_refill(counter, "oslo", Money(1000, "NOK"))
        complete_refill(counter, "oslo", Money(500, "NOK"))
        complete_refill(counter, "blr", Money(2000, "INR"))
        complete_refill(counter, "blr", Money(3000, "INR"))

        report = counter.monthly_report(2026, 11, "EUR", RATES_TO_EUR)

        self.assertEqual(report["Oslo"], Money(1500, "NOK"))
        self.assertEqual(report["Bengaluru"], Money(5000, "INR"))
        # 1,500 x 0.085 = 127.50 EUR, 5,000 x 0.0105 = 52.50 EUR
        self.assertEqual(report["Total"], Money("180.00", "EUR"))


if __name__ == "__main__":
    unittest.main()
