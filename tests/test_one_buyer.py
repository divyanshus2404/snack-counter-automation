"""Rule: two people cannot both commit to the same refill."""
import threading
import unittest

from snack import Money, RefillError, State

from .common import RECEIPT, make_counter


class OneBuyerTest(unittest.TestCase):
    def test_two_people_clicking_at_the_same_moment_only_one_wins(self):
        counter = make_counter()
        counter.set_in_office("oslo", [])  # nobody to ask, so it's open to everyone
        refill = counter.report_empty("oslo")
        self.assertTrue(refill.open_to_all)

        people = ["o1", "o2", "o3", "o4"]
        start = threading.Barrier(len(people))
        winners = []

        def click(person):
            start.wait()  # everyone clicks at exactly the same time
            try:
                counter.accept(refill.id, person)
                winners.append(person)
            except RefillError:
                pass

        threads = [threading.Thread(target=click, args=(p,)) for p in people]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(winners), 1)
        self.assertEqual(refill.buyer, winners[0])

    def test_second_person_is_told_someone_else_is_buying(self):
        counter = make_counter()
        counter.set_in_office("oslo", [])
        refill = counter.report_empty("oslo")
        counter.accept(refill.id, "o1")
        with self.assertRaises(RefillError):
            counter.accept(refill.id, "o2")

    def test_reporting_empty_twice_does_not_create_a_second_refill(self):
        counter = make_counter()
        first = counter.report_empty("oslo")
        second = counter.report_empty("oslo")
        self.assertIs(first, second)
        self.assertEqual(len(counter.refills), 1)

    def test_you_cannot_accept_an_offer_made_to_someone_else(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        self.assertEqual(refill.asked, "o1")
        with self.assertRaises(RefillError):
            counter.accept(refill.id, "o2")

    def test_only_the_buyer_can_upload_the_receipt(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        counter.accept(refill.id, "o1")
        with self.assertRaises(RefillError):
            counter.record_purchase(refill.id, "o2", Money(500, "NOK"), RECEIPT)

    def test_full_journey_empty_to_reimbursed(self):
        counter = make_counter()
        refill = counter.report_empty("oslo")
        counter.accept(refill.id, "o1")
        counter.record_purchase(refill.id, "o1", Money(850, "NOK"), RECEIPT)
        self.assertEqual(refill.state, State.CLAIM_SENT)

        claim = counter.hr.claims[refill.claim_id]
        self.assertEqual(claim["employee_id"], "EMP-O1")
        self.assertEqual(claim["currency"], "NOK")
        self.assertEqual(claim["receipt"], RECEIPT)

        counter.hr.approve(refill.claim_id)
        counter.check_hr()
        self.assertEqual(refill.state, State.REIMBURSED)


if __name__ == "__main__":
    unittest.main()
