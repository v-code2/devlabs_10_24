# Runway + Future Fund

A Cubbie Skill that shows a student what a purchase costs their savings goal and what they can safely spend each day until payday. It shows the trade-off and the student decides.

- **Future Fund (goals):** does the monthly amount reach the goal, what one purchase does to the date, and a side-by-side of buying now, waiting, or a cheaper option.
- **Runway (daily cash):** a "safe to spend today" number, how a bill changes it, and how to stretch an aid refund to the next payday.
- **Check-ins, only after the student says yes:** a morning daily number, a Sunday recap, and a 48-hour "do you still want it?" text.

No bank logins, no moving money, no investment picks. All the math is in one script, so a number is never a guess.

## The three-message demo

1. "I want to save $12,000 for graduate school in three years. I have $1,500 saved and can put away $250 a month."
   - $250 a month takes 42 months. In 36 months it reaches $10,500, $1,500 short. About $292 a month hits the date.
2. "I'm thinking about buying a $300 concert ticket. How would that affect my goal?"
   - Pushes the goal back 1.2 months, from 42 to 43.2.
3. "Compare buying it now, waiting two months, and choosing a $100 alternative."
   - Buy now and wait land on the same date at 0% interest (+1.2 months). The $100 alternative is +0.4 months.

## Try it without Cubbie

```bash
python3 scripts/runway.py goal --target 12000 --saved 1500 --monthly 250 --months 36 --today 2026-10-24
python3 scripts/runway.py buy --target 12000 --saved 1500 --monthly 250 --cost 300 --item "The ticket"
python3 scripts/runway.py compare --target 12000 --saved 1500 --monthly 250 \
  --option "Buy now:300:0" --option "Wait 2 months:300:2" --option "Cheaper:100:0"
python3 scripts/runway.py daily --sample --today 2026-10-24
python3 scripts/runway.py refund --sample --today 2026-10-24 --refund 900 --to-goal 0,200,400
```

`--sample` uses `assets/sample.json` and never reads or writes the student's saved numbers. Real numbers are saved under `~/.config/runway-future-fund/state.json` (override with `RUNWAY_DATA_DIR`).

No packages to install: Python 3.9 or newer, standard library only.

## Tests

```bash
python3 -m unittest discover -s tests
```

`tests/skill_tests.json` holds 11 texts for the stress-test script, which sends them to your own Cubbie:

```bash
python3 cubbie_stress_test.py --to "<Cubbie's number>" --skill-file tests/skill_tests.json --categories skill
```

## Install on Cubbie

Put this folder in a public GitHub repository, then text Cubbie: "Install this as a Skill:" followed by the repository link.

## Formulas

- Months to goal: the pot starts at the amount saved and grows by the monthly amount; the last month is counted as a fraction. Interest is 0% unless the student gives a yearly rate.
- Monthly amount needed: (target - saved) / months, rounded up to a whole dollar.
- Purchase delay: months to goal with the purchase taken out, minus months to goal without it.
- Daily number: (balance - bills - buffer - goal reserve) / days until payday, rounded down to a whole dollar.
