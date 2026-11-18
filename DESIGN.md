# Snack Counter Automation — Design

## The idea in one line

The problem isn't buying snacks, it's that **nobody owns the empty box**. So I automate the *coordination*: the system picks exactly one person to refill, gives them a limit and a deadline, hands it on if they don't follow through, and sends their HR claim for them. People still choose and buy the snacks.

Everything happens in the company chat tool, so there's no new app to learn.

## How a refill goes from "empty" to "reimbursed"

```
1. Someone taps "Box is empty" in chat
2. System checks the budget and sets a spending cap
3. System asks ONE person who is in the office today ("Can you buy? 2 hours to reply")
       - says no, or no reply in 2 hours  →  ask the next person
       - nobody left to ask               →  post in the office channel: first to accept gets it
4. Someone accepts → everyone else is locked out; channel says "X is buying"
       - not bought within 24 hours       →  handed to the next person
5. Buyer uploads the receipt → claim sent to HR automatically
6. HR approves (1–10 days) → buyer gets a "you've been paid" message
```

States: `LOOKING_FOR_BUYER → BUYER_COMMITTED → CLAIM_SENT → REIMBURSED`

## Main parts and the data each keeps

| Part | What it does | Data it keeps |
|---|---|---|
| **Snack counter** (`service.py`) | All the rules above | Refills, who is in each office today |
| **Refill** (`models.py`) | One trip to the shop | Office, state, cap, who was asked, who was skipped, buyer, deadline, amount, HR claim ID |
| **Office** | Settings per office | Currency, monthly budget, max purchase, chat channel |
| **Volunteer** | A person who can refill | Name, HR employee ID |
| **Fake chat / fake HR** (`fakes.py`) | Stand-ins for the real systems | Messages sent, claims submitted |

## How each problem is solved

| Problem | Solution |
|---|---|
| Box sits empty; everyone assumes someone else will do it | One **named** person is asked, with a time limit. If they don't act, it moves on automatically. |
| Two people buy on the same day | Only **one open refill per office**, and only **one person can accept** it (checked and updated in one locked step). The channel announces who's buying. |
| The same few people do most refills and wait weeks | **Fairness rule:** whoever has done the fewest refills is asked first. The **HR claim is sent instantly** from the receipt, so there's no forgotten paperwork. |
| Nobody knows the spending | Every purchase is recorded, so the **monthly report** (per office, plus one combined total) is generated automatically. |

## Assumptions (and why)

1. **Each office's budget is in its own currency** (Oslo NOK, Bengaluru INR), and receipts must be in that currency. *Why:* that's how the budgets are given, and it avoids exchange-rate errors.
2. **A visitor's purchase counts against the office they bought for**, and the claim goes to HR in the receipt currency; HR pays them in their payroll currency. *Why:* the snacks are for that office, and the brief says HR reimburses in payroll currency, so conversion is HR's job.
3. **The combined monthly total uses one exchange rate per currency**, given each month (e.g. by finance). *Why:* NOK and INR can't be added directly, and a stated rate makes the number easy to check.
4. **We know who is in each office today**, e.g. from a morning "I'm in" chat check-in. *Why:* volunteers are hybrid, so a fixed rota would often pick someone who is at home.
5. **2 hours to reply, 24 hours to buy.** *Why:* long enough to fit around work, short enough that the box isn't empty for days.
6. **The typical maximum purchase is the cap for one refill** (1,200 NOK / 3,000 INR), reduced if less budget is left. Receipts over the cap are refused. *Why:* it keeps every refill inside the budget, and the buyer knows the limit before shopping.
7. **When the monthly budget is used up, the box stays empty until next month.** *Why:* the budget is a limit, not a target.
8. **"Fair" means fewest refills bought so far.** *Why:* simple to understand and explain, and it spreads the work.
9. **HR approves claims** (rejections are handled by hand). *Why:* the brief describes approval taking 1–10 days, not rejection.
10. **Times are each office's local time.** *Why:* "this month" should mean the office's month.

## Trade-offs

- **Ask one person vs. ask everyone.** Asking everyone is faster but recreates "someone else will do it". Asking one person creates ownership; asking everyone is only the fallback.
- **Refuse over-cap receipts vs. allow them.** Refusing is strict, but the buyer is told the limit up front, and it keeps the budget simple and safe.
- **Simulated chat and HR.** As asked in the brief. The logic only talks to them through a few simple functions, so real ones can replace them.

## What I deliberately did not build

- **Sensors in the snack box**: a chat button gives the same signal for free.
- **Receipt scanning (OCR)**: the buyer types the amount; HR checks the photo anyway.
- **Our own payment system**: HR already handles approval and payroll.
- **A dashboard**: management asked for one monthly report.
- **A database and real integrations**: kept in memory to focus on getting the rules right.
- **Working hours, holidays, and reminders**: first things I'd add next (see below).

## What I'd add next

1. Timers that only count office hours, so a box reported on Friday evening doesn't time out over the weekend.
2. A daily reminder to the office coordinator if a refill is still open.
3. A "can't do it anymore" button after accepting.
4. Tracking which snacks were bought, to learn what actually gets eaten.
