# Park & Go

A Cubbie Skill that gets a student from "I'm driving to campus" to parked, with no surprise on the bill. ASU Tempe campus only.

Text Cubbie where you're going and how long you'll stay. Cubbie replies with where to park, what it will cost for your stay, and a Maps link. It can also text you 10 minutes before the price steps up, and remember where you parked (send a photo of the level) so "where did I park?" gets an answer later.

## What it does

- Picks a garage for your destination from ASU's own pages (the Memorial Union uses the Apache Boulevard Parking Structure).
- Works out the exact garage price for your stay with a small script, using ASU's hourly tiers: $4 up to 1 hour, $8 up to 2, $12 up to 3, $16 up to 4 and the $16 maximum after that.
- Offers price-step reminders, created only after you say yes.
- Remembers where you parked and what it costs so far.

## What it never does

- Pay for you. At a garage you pay at the exit machine; Cubbie hands you the browser for any payment page.
- Say how many spaces are open. It can't see live availability.
- Give written turn-by-turn directions. It sends a Maps link.

## Install

Text Cubbie the link to this repository's folder and say yes when it asks to fetch the Skill. No sign-in and no keys are needed.

## Rates

`assets/rates.json` holds the rates copied from ASU Parking and Transportation Services' daily and hourly page (https://cfo.asu.edu/daily-and-hourly) on 2026-10-24. Cubbie reads the live page first and passes any difference to the script, so a rate change does not need a code change. Lot prices are estimates because ASU does not say how part hours are billed.

## Test

```bash
python3 scripts/parking_cost.py --sample
python3 -m unittest discover -s tests
```

`tests/skill_tests.json` holds test texts for Cubbie, in the format used by the team's stress-test script.
