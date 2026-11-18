"""Monthly management report.

Each office is reported in its own currency (that's what its budget is in).
The cross-office total is converted with explicit, stated rates - one rate per
currency for the month, supplied by finance - so the number is reproducible.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from . import budget
from .models import Office, Refill, RefillState, SPENT_STATES, Volunteer
from .money import Money, total


@dataclass
class OfficeMonth:
    office: Office
    budget: Money
    spent: Money
    remaining: Money
    refill_count: int
    spent_by_buyer: dict[str, Money]
    top_items: list[tuple[str, int]]
    avg_days_to_reimburse: Optional[float]
    avg_hours_until_empty_again: Optional[float]
    claims_still_open: int


@dataclass
class MonthlyReport:
    year: int
    month: int
    report_currency: str
    rates: dict[str, Decimal]
    offices: list[OfficeMonth]
    total: Money

    def render(self) -> str:
        lines = [f"Snack spending {self.year}-{self.month:02d}", ""]
        for o in self.offices:
            lines.append(
                f"{o.office.name}: spent {o.spent} of {o.budget} ({o.remaining} left), {o.refill_count} refills"
            )
            if o.top_items:
                lines.append("  most bought: " + ", ".join(f"{name} x{n}" for name, n in o.top_items))
            if o.avg_days_to_reimburse is not None:
                lines.append(f"  avg days purchase -> reimbursed: {o.avg_days_to_reimburse:.1f}")
            if o.avg_hours_until_empty_again is not None:
                lines.append(f"  avg hours until box empty again: {o.avg_hours_until_empty_again:.0f}")
            if o.claims_still_open:
                lines.append(f"  claims still waiting on HR: {o.claims_still_open}")
        rates = ", ".join(f"1 {c} = {r} {self.report_currency}" for c, r in sorted(self.rates.items()))
        lines += ["", f"TOTAL: {self.total}   (rates: {rates})"]
        return "\n".join(lines)


def monthly_report(
    offices: Iterable[Office],
    volunteers: dict[str, Volunteer],
    refills: Iterable[Refill],
    year: int,
    month: int,
    report_currency: str,
    rates: dict[str, Decimal],
) -> MonthlyReport:
    refills = list(refills)
    report_currency = report_currency.upper()
    office_rows: list[OfficeMonth] = []
    converted: list[Money] = []

    for office in offices:
        in_month = [
            r
            for r in refills
            if r.office_id == office.id
            and r.state in SPENT_STATES
            and r.purchase
            and budget.month_key(office, r.purchase.purchased_at) == (year, month)
        ]
        spent = budget.spent_in_month(office, refills, year, month)

        by_buyer: dict[str, Money] = {}
        items: Counter[str] = Counter()
        reimburse_days: list[float] = []
        empty_again_hours: list[float] = []
        for r in in_month:
            name = volunteers[r.buyer_id].name
            by_buyer[name] = by_buyer.get(name, Money.zero(office.currency)) + r.purchase.amount
            items.update(i.strip().lower() for i in r.purchase.items)
            if r.state == RefillState.REIMBURSED and r.resolved_at:
                reimburse_days.append((r.resolved_at - r.purchase.purchased_at).total_seconds() / 86400)
            nxt = min(
                (x.reported_at for x in refills if x.office_id == office.id and x.reported_at > r.purchase.purchased_at),
                default=None,
            )
            if nxt:
                empty_again_hours.append((nxt - r.purchase.purchased_at).total_seconds() / 3600)

        if office.currency != report_currency and office.currency not in rates:
            raise KeyError(f"no exchange rate for {office.currency} -> {report_currency}")
        converted.append(spent.convert(report_currency, rates.get(office.currency, Decimal(1))))

        office_rows.append(
            OfficeMonth(
                office=office,
                budget=office.monthly_budget,
                spent=spent,
                remaining=office.monthly_budget - spent,
                refill_count=len(in_month),
                spent_by_buyer=by_buyer,
                top_items=items.most_common(5),
                avg_days_to_reimburse=sum(reimburse_days) / len(reimburse_days) if reimburse_days else None,
                avg_hours_until_empty_again=sum(empty_again_hours) / len(empty_again_hours) if empty_again_hours else None,
                claims_still_open=sum(1 for r in in_month if r.state != RefillState.REIMBURSED),
            )
        )

    return MonthlyReport(year, month, report_currency, dict(rates), office_rows, total(converted, report_currency))
