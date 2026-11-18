"""Refill lifecycle: empty -> reimbursed, and the 'only one buyer' rule."""
import threading
import unittest
from datetime import timedelta

from snack import AlreadyTaken, InvalidState, Money, NotOfferedToYou, NotYourRefill, RefillState

from .helpers import RECEIPT, World


class HappyPathTest(unittest.TestCase):
    def test_empty_to_reimbursed(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        self.assertEqual(r.state, RefillState.SEEKING_BUYER)
        self.assertEqual(r.offered_to, "o1")  # deterministic tie-break when nobody has bought yet
        self.assertEqual(r.spend_cap, Money(1200, "NOK"))

        w.svc.accept(r.id, "o1")
        self.assertEqual(r.state, RefillState.COMMITTED)

        w.clock.advance(timedelta(hours=3))
        w.svc.record_purchase(r.id, "o1", Money(850, "NOK"), RECEIPT, ["chips", "fruit"])
        self.assertEqual(r.state, RefillState.CLAIM_SUBMITTED)

        claim = w.hr.claims[r.claim_id]
        self.assertEqual((claim.employee_id, claim.amount, claim.currency), ("EMP-O1", Money(850, "NOK").amount, "NOK"))
        self.assertEqual(claim.receipt_image, RECEIPT)

        w.clock.advance(timedelta(days=3))
        w.svc.tick()
        self.assertEqual(r.state, RefillState.CLAIM_SUBMITTED)  # HR hasn't decided yet
        w.hr.approve(r.claim_id)
        w.svc.tick()
        self.assertEqual(r.state, RefillState.REIMBURSED)
        self.assertTrue(any("approved" in m for m in w.chat.to("@o1")))

    def test_duplicate_empty_reports_join_the_same_refill(self):
        w = World()
        first = w.svc.report_empty("oslo", "o3")
        second = w.svc.report_empty("oslo", "o4")
        self.assertIs(first, second)
        self.assertEqual(len(w.svc.refills), 1)
        offers = [m for m in w.chat.messages if m.direct and "your turn" in m.text]
        self.assertEqual(len(offers), 1)

    def test_offices_are_independent(self):
        w = World()
        a = w.svc.report_empty("oslo", "o3")
        b = w.svc.report_empty("blr", "b3")
        self.assertIsNot(a, b)
        self.assertEqual(b.spend_cap, Money(3000, "INR"))

    def test_new_refill_allowed_once_previous_is_bought(self):
        w = World()
        first = w.full_refill("oslo", Money(500, "NOK"), approve=False)
        second = w.svc.report_empty("oslo", "o3")
        self.assertIsNot(first, second)


class OnlyOneBuyerTest(unittest.TestCase):
    def test_two_people_cannot_both_commit_concurrently(self):
        # Nobody is in the office -> the refill is broadcast and anyone may grab it.
        w = World(present={})
        r = w.svc.report_empty("oslo", "o1")
        self.assertTrue(r.broadcast)

        contenders = ["o1", "o2", "o3", "o4", "b1", "b2"]
        barrier = threading.Barrier(len(contenders))
        winners, losers = [], []

        def grab(vid):
            barrier.wait()
            try:
                w.svc.accept(r.id, vid)
                winners.append(vid)
            except AlreadyTaken:
                losers.append(vid)

        threads = [threading.Thread(target=grab, args=(v,)) for v in contenders]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), len(contenders) - 1)
        self.assertEqual(r.buyer_id, winners[0])
        self.assertEqual(r.state, RefillState.COMMITTED)

    def test_second_accept_is_rejected(self):
        w = World(present={})
        r = w.svc.report_empty("oslo", "o1")
        w.svc.accept(r.id, "o2")
        with self.assertRaises(AlreadyTaken):
            w.svc.accept(r.id, "o3")

    def test_cannot_accept_an_offer_made_to_someone_else(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        self.assertEqual(r.offered_to, "o1")
        with self.assertRaises(NotOfferedToYou):
            w.svc.accept(r.id, "o2")

    def test_only_the_buyer_can_record_the_purchase(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        w.svc.accept(r.id, "o1")
        with self.assertRaises(NotYourRefill):
            w.svc.record_purchase(r.id, "o2", Money(500, "NOK"), RECEIPT)

    def test_cannot_record_purchase_before_committing(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        with self.assertRaises(InvalidState):
            w.svc.record_purchase(r.id, "o1", Money(500, "NOK"), RECEIPT)

    def test_receipt_is_required(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        w.svc.accept(r.id, "o1")
        with self.assertRaises(ValueError):
            w.svc.record_purchase(r.id, "o1", Money(500, "NOK"), b"")


if __name__ == "__main__":
    unittest.main()
