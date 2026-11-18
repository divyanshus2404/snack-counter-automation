# Snack Counter Automation

Coordinates snack-box refills for the Oslo and Bengaluru offices: picks exactly one volunteer who is in the office, gives them a budget cap and deadline, reassigns if they don't follow through, files the HR claim from the receipt, and produces the monthly spend report across both currencies.

- **Design:** [DESIGN.md](DESIGN.md)
- **Core logic:** [`snack/`](snack) — Python 3.10+, standard library only
- **Tests:** [`tests/`](tests)

## Run

```bash
python3 -m unittest discover -s tests -t . -v   # 45 tests
python3 demo.py                                 # simulated week + monthly report
```

## Layout

| File | What it does |
|---|---|
| `snack/service.py` | Refill lifecycle state machine and scheduler (`tick`) |
| `snack/selection.py` | Who gets asked to buy (presence + fair rotation) |
| `snack/budget.py` | Budget check with reservations, per office currency and local month |
| `snack/report.py` | Monthly management report with explicit FX rates |
| `snack/money.py` | Currency-safe decimal money |
| `snack/ports.py` | Chat, HR, availability, clock interfaces + in-memory fakes |
| `snack/config.py` | The two offices' budgets and ranges |

## Rules covered by tests

| Rule | Test file |
|---|---|
| Two people cannot both commit to the same refill (threaded race) | `test_lifecycle.py` |
| Duplicate "empty" reports join the open refill | `test_lifecycle.py` |
| Unanswered / declined offers move to the next person; missed buy deadline releases the buyer | `test_reassignment.py` |
| Nobody available → broadcast → coordinator escalation (once) | `test_reassignment.py` |
| Only volunteers present at that office are asked; visitors count; fair rotation | `test_selection.py` |
| Cap, reservation, exhaustion until next month, over-cap review, wrong-currency receipt | `test_budget.py` |
| Month boundary in office local time; visitor spend charged to the right office | `test_budget.py` |
| Per-office totals + converted total; no cross-currency arithmetic; missing rate errors | `test_report_and_hr.py` |
| HR outage retried without duplicate claims; slow claims nudged; rejections notified | `test_report_and_hr.py` |
