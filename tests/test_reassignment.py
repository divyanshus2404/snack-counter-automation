"""A refill nobody completes is handed to someone else."""
import unittest
from datetime import timedelta

from snack import InvalidState, Money, NotOfferedToYou, RefillState

from .helpers import RECEIPT, World


class ReassignmentTest(unittest.TestCase):
    def test_unanswered_offer_moves_to_next_person(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        self.assertEqual(r.offered_to, "o1")

        w.clock.advance(timedelta(hours=1, minutes=59))
        w.svc.tick()
        self.assertEqual(r.offered_to, "o1")  # not yet

        w.clock.advance(timedelta(minutes=1))
        w.svc.tick()
        self.assertEqual(r.offered_to, "o2")
        self.assertIn("o1", r.passed_over)
        with self.assertRaises(NotOfferedToYou):
            w.svc.accept(r.id, "o1")  # late click on the stale offer

    def test_decline_moves_to_next_person(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        w.svc.decline(r.id, "o1")
        self.assertEqual(r.offered_to, "o2")

    def test_committed_but_not_bought_is_released_and_reoffered(self):
        w = World()
        r = w.svc.report_empty("oslo", "o3")
        w.svc.accept(r.id, "o1")

        w.clock.advance(timedelta(hours=24))
        w.svc.tick()

        self.assertEqual(r.state, RefillState.SEEKING_BUYER)
        self.assertIsNone(r.buyer_id)
        self.assertEqual(r.offered_to, "o2")
        self.assertTrue(any("handed to someone else" in m for m in w.chat.to("@o1")))
        with self.assertRaises(InvalidState):
            w.svc.record_purchase(r.id, "o1", Money(500, "NOK"), RECEIPT)

        # The new person can complete it.
        w.svc.accept(r.id, "o2")
        w.svc.record_purchase(r.id, "o2", Money(500, "NOK"), RECEIPT)
        self.assertEqual(r.state, RefillState.CLAIM_SUBMITTED)
        self.assertEqual(w.hr.claims[r.claim_id].employee_id, "EMP-O2")

    def test_everyone_passes_then_broadcast_then_coordinator(self):
        w = World(present={"oslo": ["o1", "o2"]})
        r = w.svc.report_empty("oslo", "o3")
        w.svc.decline(r.id, "o1")
        w.svc.decline(r.id, "o2")
        self.assertTrue(r.broadcast)
        self.assertTrue(any("First volunteer" in m for m in w.chat.to("#snacks-oslo")))

        w.clock.advance(timedelta(hours=4))
        w.svc.tick()
        w.clock.advance(timedelta(hours=4))
        w.svc.tick()
        escalations = [m for m in w.chat.to("@oslo-coordinator") if "Nobody has picked up" in m]
        self.assertEqual(len(escalations), 1)  # escalated once, not spammed

        # Anyone can still take it from the broadcast, even someone who declined earlier.
        w.svc.accept(r.id, "o1")
        self.assertEqual(r.state, RefillState.COMMITTED)

    def test_nobody_in_office_goes_straight_to_broadcast(self):
        w = World(present={})
        r = w.svc.report_empty("blr", "b1")
        self.assertTrue(r.broadcast)
        self.assertIsNone(r.offered_to)


if __name__ == "__main__":
    unittest.main()
