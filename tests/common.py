from datetime import datetime

from snack import BENGALURU, OSLO, FakeChat, FakeClock, FakeHR, SnackCounter, Volunteer

RECEIPT = b"receipt photo"


def make_counter():
    """Two offices, four volunteers each, everyone in their home office today."""
    volunteers = [Volunteer(f"o{i}", f"Oslo {i}", f"EMP-O{i}") for i in range(1, 5)]
    volunteers += [Volunteer(f"b{i}", f"Blr {i}", f"EMP-B{i}") for i in range(1, 5)]
    counter = SnackCounter([OSLO, BENGALURU], volunteers, FakeChat(), FakeHR(), FakeClock(datetime(2026, 11, 16, 9, 0)))
    counter.set_in_office("oslo", ["o1", "o2", "o3", "o4"])
    counter.set_in_office("blr", ["b1", "b2", "b3", "b4"])
    return counter


def complete_refill(counter, office_id, amount):
    """Run one refill from 'empty' to 'claim sent'."""
    refill = counter.report_empty(office_id)
    buyer = refill.asked
    counter.accept(refill.id, buyer)
    counter.record_purchase(refill.id, buyer, amount, RECEIPT)
    return refill
