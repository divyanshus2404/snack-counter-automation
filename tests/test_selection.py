"""Choosing who buys: present today, not busy, fair rotation."""
import unittest
from datetime import timedelta

from snack import Money

from .helpers import World


class SelectionTest(unittest.TestCase):
    def test_only_people_in_that_office_today_are_asked(self):
        w = World(present={"oslo": ["o3"]})  # o1, o2, o4 are at home / on holiday
        r = w.svc.report_empty("oslo", "o3")
        self.assertEqual(r.offered_to, "o3")

    def test_volunteer_on_holiday_is_skipped(self):
        w = World()
        w.away("o1")
        r = w.svc.report_empty("oslo", "o3")
        self.assertEqual(r.offered_to, "o2")

    def test_visitor_from_other_office_can_be_asked(self):
        w = World(present={"oslo": ["b2"]})  # a Bengaluru volunteer visiting Oslo this week
        r = w.svc.report_empty("oslo", "o1")
        self.assertEqual(r.offered_to, "b2")

    def test_visitor_is_not_asked_by_home_office(self):
        w = World(present={"oslo": ["b2"], "blr": ["b1"]})
        r = w.svc.report_empty("blr", "b1")
        self.assertEqual(r.offered_to, "b1")

    def test_rotation_spreads_refills_across_volunteers(self):
        w = World()
        buyers = []
        for _ in range(4):
            r = w.full_refill("oslo", Money(400, "NOK"))
            buyers.append(r.buyer_id)
            w.clock.advance(timedelta(days=2))
        self.assertEqual(sorted(buyers), ["o1", "o2", "o3", "o4"])

    def test_person_still_waiting_for_money_is_asked_last(self):
        w = World(present={"oslo": ["o1", "o2"]})
        w.full_refill("oslo", Money(400, "NOK"), approve=True)       # o1 bought, already reimbursed
        w.clock.advance(timedelta(days=1))
        w.full_refill("oslo", Money(400, "NOK"), approve=False)      # o2 bought, still waiting on HR
        w.clock.advance(timedelta(days=1))
        r = w.svc.report_empty("oslo", "o1")
        self.assertEqual(r.offered_to, "o1")  # o2 is out of pocket, so o1 goes first despite equal counts

    def test_someone_busy_with_another_refill_is_not_offered_a_second(self):
        # b1 is visiting Oslo but has committed to the Bengaluru refill (e.g. buying before flying back).
        w = World(present={"blr": ["b1"], "oslo": ["o1"]})
        blr = w.svc.report_empty("blr", "b2")
        w.svc.accept(blr.id, "b1")
        w.at_office("oslo", ["b1"])  # now b1 is in Oslo
        w.away("o1")
        oslo = w.svc.report_empty("oslo", "o2")
        self.assertIsNone(oslo.offered_to)
        self.assertTrue(oslo.broadcast)


if __name__ == "__main__":
    unittest.main()
