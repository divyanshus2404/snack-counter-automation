# Snack Counter Automation — Design

## What "automate" means here

The problems are not "buying is manual", they are **nobody owns the empty box**, **two people own it at once**, **the same few people carry the cost** and **nobody can see the money**. So the system automates *coordination and paperwork*, not shopping: it picks exactly one person who is physically in the office, gives them a spending cap and a deadline, files their HR claim the moment they upload a receipt, and keeps a ledger that produces the monthly report. People still choose and buy the snacks.

Everything happens inside the chat tool people already use (a bot with buttons), so there's no new app to adopt.

## Lifecycle: from "empty" to "reimbursed"

```
"Box is empty" (anyone, chat button / QR on the box)
   │  duplicate reports join the open refill
   ▼
budget check ──not enough left──▶ WAITING_FOR_BUDGET ──new month──┐
   │ reserve cap = min(max typical purchase, budget left)          │
   ▼                                                               │
SEEKING_BUYER ◀────────────────────────────────────────────────────┘
   │ DM the top-ranked volunteer who is in that office today: [I'll buy] [Can't today], 2 h to answer
   │ decline / no answer → next person;  nobody left → post in office channel, first tap wins;
   │ still nobody after 4 h → coordinator is pinged (once)
   ▼ accept (atomic: only one person can win)
COMMITTED  — buyer has cap + 24 h deadline; channel told "X is on it"
   │ deadline missed → buyer released (told not to buy), back to SEEKING_BUYER, next person
   ▼ upload receipt photo + amount (+ optional item list)
   ├── over cap ─▶ NEEDS_REVIEW ── coordinator approves ─┐
   ▼                                                     ▼
PURCHASED ──claim sent to HR (retried if HR is down)──▶ CLAIM_SUBMITTED
                                                         │ poll HR; nudge coordinator after 7 days
                                                         ├─▶ REIMBURSED
                                                         └─▶ CLAIM_REJECTED (coordinator follows up)
```

## Main parts and the data each keeps

| Part | Responsibility | Data |
|---|---|---|
| **Refill service** (`service.py`) | The state machine above; the only thing allowed to change a refill | `Refill`: office, state, reporter, offered-to + expiry, passed-over set, buyer + deadline, spend cap, purchase (amount, receipt, items, time), HR claim id, timestamps, event history |
| **Buyer selection** (`selection.py`) | Pure function: rank eligible volunteers | Reads volunteers, today's location, refill history |
| **Budget** (`budget.py`) | Remaining = budget − spent this month − open reservations, in the office's currency | Office config: currency, timezone, monthly budget, min/max purchase |
| **Scheduler** (`tick()`) | Every few minutes: expire offers and commitments, retry HR, sync claim status, release budget holds at month start | none of its own |
| **Report** (`report.py`) | Monthly per-office spend in local currency + one total at stated rates; top items; days to reimbursement; hours until empty again | Read-only over refills |
| **Ports** (`ports.py`) | Chat, HR, availability, clock as interfaces with in-memory fakes | Fakes record messages/claims |

Volunteer record: id, name, HR employee ID, chat ID, home office, payroll currency. **Availability** ("who is at which office today") is an input port — in production fed by desk booking / calendar or a morning "I'm in today" chat check-in.

## How each problem is prevented

| Problem | Mechanism | Test |
|---|---|---|
| Box sits empty, everyone assumes someone else | One named person is asked at a time, with a timeout; refusal or silence moves it on automatically; a broadcast then a coordinator escalation are the safety nets | `test_reassignment.py` |
| Two people buy the same day | One active refill per office (duplicate reports join it); `accept` is check-and-set under a lock (a conditional `UPDATE … WHERE state='seeking_buyer'` in a DB); channel announces the owner; a released buyer is told not to buy and can no longer submit for that refill | `test_two_people_cannot_both_commit_concurrently` (6 threads, 1 winner) |
| Same few people do it all / wait weeks | Rotation: fewest refills in last 90 days, then longest since last one; anyone still waiting for money is asked last. Claim is filed instantly from the receipt with no manual HR form; claims pending > 7 days ping the coordinator; report shows avg days to reimbursement | `test_rotation_spreads…`, `test_person_still_waiting…`, `test_slow_claim_nudges…` |
| Nobody knows spend / what gets eaten | Every purchase is in the ledger with items; monthly report per office + converted total; "hours until empty again" as a cheap consumption signal | `test_report_and_hr.py` |

**Money rules.** `Money` refuses to add or compare different currencies, so a NOK + INR bug fails loudly. Budgets are checked only in the office's own currency. The month is the office's local month (a 00:30 IST purchase on 1 Dec is December). A visitor's purchase is charged to the office whose box they filled, and the claim is sent in the receipt currency; HR pays out in their payroll currency (that conversion is HR's, not ours). The cross-office total uses one explicit rate per currency per month, printed in the report; a missing rate is an error, never a silent zero. Pending claims count as spend (the money is gone); rejected ones don't.

## Trade-offs

- **Ask one person at a time vs. broadcast to all.** Directed asks create ownership and stop the "someone else will" effect, but are slower if people ignore them. 2 h timeouts keep it moving; broadcast is only the fallback.
- **Reserve the full cap up front.** Can block a last small refill near month-end even if the actual spend would have fit. I prefer that over overspending; the coordinator can still approve over-cap receipts.
- **Over-cap receipts are reviewed, not rejected.** The volunteer has already spent their own money; refusing them would kill goodwill.
- **Polling HR instead of webhooks.** We don't control the vendor; polling every few minutes is simple and robust. Claim submission uses an idempotency key (refill id) so retries never double-claim.
- **Strict release on a missed deadline.** If a released buyer buys anyway, they claim via HR manually. Simpler and guarantees no double purchase through the system.
- **Single process, one lock.** Fine for ~35 volunteers and two boxes; the same rules map onto a DB row with conditional updates.

## Deliberately not building

- **Stock sensors / smart shelves** — a button on the box (QR → chat) gives the same signal for free.
- **Ordering/delivery integration or a snack catalogue** — volunteers know what sells; item lists on receipts are enough to learn it.
- **OCR of receipts** — the buyer types the amount; HR already checks the image.
- **Our own reimbursement or payment** — HR owns approval and payroll currency; we only file and track.
- **A web dashboard** — management asked for one monthly report; it's generated text/email.
- **Gamification, ratings, budget forecasting** — not asked for, adds noise.

## Assumptions / questions I would confirm

1. Can the HR API accept an idempotency key and expose claim status (poll or webhook)? If not, we dedupe on our side and rely on HR notifications.
2. Does the claim go in the **receipt** currency (my assumption) or must we pre-convert to payroll currency?
3. Which currency and which rate source (e.g. Norges Bank / finance month-end rate) does management want the total in?
4. Is there a reliable "who is in the office today" source (desk booking, badge data)? If not, a daily chat check-in.
5. Are the typical purchase ranges hard caps, or guidance? I treat the max as a soft cap with coordinator override.
6. Is there one coordinator per office who can approve exceptions?
