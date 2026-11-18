"""Rule: a refill nobody completes is handed to someone else."""
import unittest

from snack import Money, RefillError, State

from .common import RECEIPT, make_counter


class HandoverTest(unittest.TestCase):
    def test_no_answer_in_2_hours_asks_the_next_person(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        self.assertEqual(refill.asked, "o1")

        counter.clock.advance(hours=1, minutes=59)
        counter.check_timeouts()
        self.assertEqual(refill.asked, "o1")  # still waiting

        counter.clock.advance(minutes=1)
        counter.check_timeouts()
        self.assertEqual(refill.asked, "o2")

    def test_saying_no_asks_the_next_person(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        counter.decline(refill.id, "o1")
        self.assertEqual(refill.asked, "o2")

    def test_accepted_but_not_bought_in_24_hours_is_handed_on(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        counter.accept(refill.id, "o1")

        counter.clock.advance(hours=24)
        counter.check_timeouts()

        self.assertEqual(refill.state, State.LOOKING_FOR_BUYER)
        self.assertEqual(refill.asked, "o2")
        self.assertIn("handed on", counter.chat.to("o1")[-1])
        with self.assertRaises(RefillError):  # o1 can no longer claim it
            counter.record_purchase(refill.id, "o1", Money(500, "NOK"), RECEIPT)

    def test_when_everyone_passes_it_is_open_to_all(self):
        counter = make_counter()
        counter.set_in_office("oslo", ["o1", "o2"])
        refill = counter.report_empty("oslo")
        counter.decline(refill.id, "o1")
        counter.decline(refill.id, "o2")

        self.assertTrue(refill.open_to_all)
        self.assertIn("First volunteer to accept", counter.chat.to("#snacks-oslo")[-1])
        counter.accept(refill.id, "o3")  # anyone can take it now
        self.assertEqual(refill.buyer, "o3")


if __name__ == "__main__":
    unittest.main()
