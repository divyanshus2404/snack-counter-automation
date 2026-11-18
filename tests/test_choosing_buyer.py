"""Rule: ask someone who is in the office today, and share the work fairly."""
import unittest

from snack import Money

from .common import complete_refill, make_counter


class ChoosingBuyerTest(unittest.TestCase):
    def test_only_people_in_the_office_today_are_asked(self):
        counter = make_counter()
        counter.set_in_office("oslo", ["o3"])  # the others are at home or on holiday
        self.assertEqual(counter.report_empty("oslo").asked, "o3")

    def test_a_visitor_from_the_other_office_can_be_asked(self):
        counter = make_counter()
        counter.set_in_office("oslo", ["b2"])  # Bengaluru volunteer visiting Oslo
        self.assertEqual(counter.report_empty("oslo").asked, "b2")

    def test_refills_rotate_so_the_same_person_is_not_always_asked(self):
        counter = make_counter()
        buyers = [complete_refill(counter, "oslo", Money(400, "NOK")).buyer for _ in range(4)]
        self.assertEqual(sorted(buyers), ["o1", "o2", "o3", "o4"])


if __name__ == "__main__":
    unittest.main()
