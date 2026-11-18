"""Walk through a month at both offices and print the chat traffic and the management report.

    python3 demo.py
"""
from datetime import timedelta
from decimal import Decimal

from snack import Money, monthly_report
from tests.helpers import RECEIPT, World


def show_new_messages(w, seen):
    for m in w.chat.messages[seen:]:
        print(f"    [{'DM ' if m.direct else ''}{m.to}] {m.text}")
    return len(w.chat.messages)


def main():
    w = World(present={"oslo": ["o1", "o2", "o3"], "blr": ["b1", "b2", "b3", "b4", "o4"]})  # o4 visiting Bengaluru
    seen = 0

    print("1. Oslo box empty; o1 is asked, ignores it, offer moves to o2")
    r = w.svc.report_empty("oslo", "o3")
    w.svc.report_empty("oslo", "o2")  # duplicate report, ignored
    w.clock.advance(timedelta(hours=2))
    w.svc.tick()
    seen = show_new_messages(w, seen)

    print("2. o2 accepts and buys")
    w.svc.accept(r.id, "o2")
    w.svc.record_purchase(r.id, "o2", Money(980, "NOK"), RECEIPT, ["chips", "fruit", "chocolate"])
    seen = show_new_messages(w, seen)

    print("3. Bengaluru empty; b1 commits but never buys; handed to b2")
    r2 = w.svc.report_empty("blr", "b3")
    w.svc.accept(r2.id, r2.offered_to)
    w.clock.advance(timedelta(hours=24))
    w.svc.tick()
    w.svc.accept(r2.id, r2.offered_to)
    w.svc.record_purchase(r2.id, r2.buyer_id, Money(2400, "INR"), RECEIPT, ["samosa", "biscuits"])
    seen = show_new_messages(w, seen)

    print("4. HR approves both claims a few days later")
    w.clock.advance(timedelta(days=4))
    for c in w.hr.claims:
        w.hr.approve(c)
    w.svc.tick()
    seen = show_new_messages(w, seen)

    print("\n5. Monthly report\n")
    rep = monthly_report(
        w.svc.offices.values(), w.svc.volunteers, w.svc.refills.values(), 2026, 11, "EUR",
        {"NOK": Decimal("0.085"), "INR": Decimal("0.0105")},
    )
    print(rep.render())

    print("\nRefill R2 history:")
    for at, event in r2.history:
        print(f"  {at:%d %b %H:%M} {event}")


if __name__ == "__main__":
    main()
