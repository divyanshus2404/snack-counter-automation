# Snack Counter Automation

Coordinates snack-box refills for the Oslo and Bengaluru offices: asks exactly one volunteer who is in the office, gives them a spending cap and a deadline, hands the refill on if they don't follow through, sends their HR claim automatically, and produces the monthly spend report across both currencies.

- **Design:** [DESIGN.md](DESIGN.md)
- **Code:** [`snack/`](snack): Python 3.10+, standard library only
- **Tests:** [`tests/`](tests)

## Run

```bash
python3 -m unittest discover -s tests -t . -v   # 23 tests
python3 demo.py                                 # walks through a few refills
```

## Files

| File | What's in it |
|---|---|
| `snack/service.py` | All the rules: the refill lifecycle, choosing who buys, the budget check, the monthly report |
| `snack/models.py` | Money, Office, Volunteer, Refill |
| `snack/fakes.py` | Simulated chat tool, HR system and clock |

## Tests

| File | Rule it proves |
|---|---|
| `test_one_buyer.py` | Two people cannot both commit to the same refill |
| `test_handover.py` | A refill nobody completes is handed to someone else |
| `test_choosing_buyer.py` | Only people in the office are asked, and the work rotates fairly |
| `test_budget.py` | Budgets and totals are correct across both currencies |
