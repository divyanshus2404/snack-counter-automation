"""Walk through a few refills and print what everyone sees.

    python3 demo.py
"""
from decimal import Decimal

from snack import Money
from tests.common import RECEIPT, make_counter

counter = make_counter()
shown = 0


def show(title):
    global shown
    print(f"\n{title}")
    for to, text in counter.chat.messages[shown:]:
        print(f"   to {to}: {text}")
    shown = len(counter.chat.messages)


oslo = counter.report_empty("oslo")
show("1. Oslo box reported empty")

counter.clock.advance(hours=2)
counter.check_timeouts()
show("2. o1 didn't reply in 2 hours")

counter.accept(oslo.id, "o2")
counter.record_purchase(oslo.id, "o2", Money(980, "NOK"), RECEIPT)
show("3. o2 accepts and buys")

blr = counter.report_empty("blr")
counter.accept(blr.id, "b1")
counter.clock.advance(hours=24)
counter.check_timeouts()
show("4. Bengaluru: b1 accepted but didn't buy within 24 hours")

counter.accept(blr.id, "b2")
counter.record_purchase(blr.id, "b2", Money(2400, "INR"), RECEIPT)
for claim_id in counter.hr.claims:
    counter.hr.approve(claim_id)
counter.check_hr()
show("5. b2 buys, and HR approves both claims")

print("\n6. Monthly report")
report = counter.monthly_report(2026, 11, "EUR", {"NOK": Decimal("0.085"), "INR": Decimal("0.0105")})
for name, amount in report.items():
    print(f"   {name}: {amount}")
