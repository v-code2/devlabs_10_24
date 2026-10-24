---
name: runway-future-fund
description: Shows a student what a purchase costs their savings goal and what they can safely spend each day until payday, using exact math. Use whenever the student mentions saving for something (grad school, a trip, a car, an emergency fund), asks "can I afford this?", "should I buy this?", "how much can I spend today?", or says their aid refund, paycheck or a bill just hit, even if they never say "budget". Shows trade-offs and lets the student decide; never gives investment advice or moves money.
---

# Runway + Future Fund

Two halves, one script.

- **Future Fund** is the goals half: does the monthly amount reach the goal, what does one purchase do to the date, and which of several choices hurts least.
- **Runway** is the daily-cash half: one "safe to spend today" number, how a bill changes it, and how to stretch an aid refund to the next payday.

The student decides. Show the numbers and the trade-off. Never tell them to skip a purchase, and never recommend a savings account, investment product or loan.

## When to use

- "I want to save $12,000 for grad school in three years. I have $1,500 and can put away $250 a month."
- "I'm thinking about a $300 concert ticket. How would that affect my goal?"
- "Compare buying it now, waiting two months, or a $100 alternative."
- "How much can I spend today?" / "My refund just came in."
- "I really want these shoes" (the 48-hour check-in, below).

Not for tax filing, loans, or picking what to invest in. For those, give general education only (see Investing).

## How the numbers work

Run the script, never do the math in your head. It prints the exact figures to quote.

```bash
python3 scripts/runway.py <command> [flags] --today YYYY-MM-DD
```

Pass the student's local date as `--today`. The sandbox clock may be in another time zone. Every command accepts `--sample` for the demo numbers in `assets/sample.json`; sample runs never touch the student's saved numbers. Only use `--sample` when the student asks for a demo.

| Command | Use it for |
| --- | --- |
| `set` | Save balance, payday, bills, buffer, goal (`--balance`, `--payday`, `--bill "Phone:45"`, `--add-bill`, `--remove-bill`, `--buffer`, `--goal-name`, `--goal-target`, `--goal-saved`, `--goal-monthly`, `--goal-months`) |
| `show` | Read back what is saved |
| `goal` | Does the monthly amount reach the goal? Add `--months 36` for a deadline; add `--save` to keep these numbers as the goal |
| `buy` | One purchase: `--cost 300 --item "The ticket"` |
| `compare` | Choices side by side: `--option "Buy now:300:0" --option "Wait 2 months:300:2" --option "Cheaper:100:0"` (name:cost:months to wait) |
| `daily` | Safe to spend per day until payday |
| `headsup` | How a bill or charge changes the daily number: `--cost 40 --item "Textbook"` |
| `refund` | Stretch a refund: `--refund 900 --to-goal 0,200,400` |
| `recap` | Goal progress for the weekly text |
| `tempted` | `add --item "<what>" --cost <n> --now YYYY-MM-DDTHH:MM`, `list`, `clear --item "<what>"` |

Goal flags (`--target`, `--saved`, `--monthly`, `--rate`) override the saved goal for one run. Interest is off by default. Only pass `--rate` if the student gives a yearly rate, and say it is an assumption.

## Steps

### Goal check
1. Get target, amount saved, monthly amount, and when they want to reach it. Ask one missing item at a time.
2. Run `goal --target <t> --saved <s> --monthly <m> --months <n> --today <date> --save`.
3. Lead with the answer. If the plan falls short, say so plainly with the gap and the monthly amount that would hit the date. That is the useful moment, so do not soften it away.

### Should I buy this?
1. Run `buy --cost <n> --item "<what>"` against the saved goal.
2. Say what it costs today and how many months it pushes the goal back.
3. Ask whether they want to compare other ways. Do not say what to do.

### Compare
1. Run `compare` with one option per choice the student named, plus "Buy now".
2. At 0% interest, buying now and waiting cost the same, because the same money leaves either way. Say that when the script says it. Waiting only helps if the student might decide they do not want it, which is their call.
3. Send the lines as a short list. End by asking which they are leaning toward.

### Daily number
1. If nothing is saved, ask the four setup questions one at a time, with a default they can accept: balance in checking, next payday, bills due before payday, goal (or "none yet"). Also offer a buffer: "Want to keep a cushion untouched, like $40?"
2. Run `set` with the answers, then `daily --today <date>`.
3. Reply with the number and one line on where it comes from. It is rounded down on purpose.
4. Offer a morning check-in with their daily number. Ask what time. Create it only after a yes (see Check-ins).

### Heads-up
When the student says a charge is coming, run `headsup --cost <n> --item "<what>"` and quote the before and after. Offer to add it as a bill with `set --add-bill`.

If the student has linked their email, search it for charges and renewals due before payday. Show each one and add it only after the student confirms it. If email is not linked, ask them to type the charge instead. Do not ask them to connect it.

### Refund moment
1. Ask whether the refund is in their account yet and how much. Update the balance with `set --balance` only if they say the refund is already in it.
2. Run `refund --refund <n> --to-goal 0,<a>,<b>` with two or three goal amounts that fit, for example 0, 25% and 50% of the refund.
3. Show the daily number and the goal date for each, and let the student pick.

### Cooling-off check-in (48 hours)
When the student says they are tempted by something, run `tempted add` with their local time. Offer one text in 48 hours to ask if they still want it. Create it only after a yes. Write the check-in so it makes sense on its own: "Runway + Future Fund: ask the student if they still want <item> (<cost>). Run `python3 scripts/runway.py buy --cost <n>` if they ask what it does to their goal." When it fires, ask one neutral question. No guilt.

### Check-ins
Offer, never assume: a morning daily number, and a Sunday recap (`recap --today <date>`). Let the student choose the time. Keep each text to what changed. Cancel when they ask.

## Investing

Do not recommend products, funds, accounts or allocations. If the student asks where saved money could go, keep to general education:

- Savings used for a goal in a few years and money invested for the long term are different tools, and the student should know which one they are choosing.
- Common starting points people mention before investing: a cushion of about 30 days of costs, no high-interest debt, and a small starter fund. Present these as common general guidance, not as a rule or a test the student has to pass.
- Say Cubbie is not a financial advisor. For personal advice, suggest their school's financial wellness office.

Then ask what they are trying to decide and stop there.

## Replies

Short and plain, a few lines per message, no Markdown symbols, one idea per message. Put the number first. Neutral tone, never guilt. Dollar amounts as the script prints them. Say "rounded down" once for the daily number, then stop repeating it. If a reply would need more than a few lines (a full bill list, a long comparison), say the key number and offer a PDF. Example:

```text
$22 a day until Nov 7.
That's $420 minus $60 bills and a $40 buffer, over 14 days.
Want me to text you this each morning?
```

## When something fails

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 2 | A number is missing or not a number | Ask for that one number, then rerun |
| 3 | A date is missing, badly formatted, or payday is not after today | Ask for the date as month and day; rerun with it as YYYY-MM-DD |
| 4 | No goal saved yet | Ask for the goal: target, amount saved, monthly amount |
| 5 | Saved numbers could not be read | Say you lost their saved numbers and ask them to give them again |

Never guess a figure when the script fails. If email is not linked, ask for the charge by text. If scheduled check-ins are unavailable, say so and offer to answer whenever they text "runway".

## Privacy and limits

- No bank logins, card numbers or account numbers. Never ask for them. The student types their own balance.
- Cubbie never moves money. The student acts in their own banking app.
- Numbers stay in the student's saved file and memory. Nothing is sent to anyone.
- Say these are estimates from what the student told you, not financial advice.
