---
name: park-and-go
description: Tells a student where to park at ASU Tempe, what it will cost for their stay, and texts them before the price steps up. Use whenever the student asks where to park, how much parking costs, how to get to a campus building by car, where they left their car, or asks to be reminded before parking gets more expensive. ASU Tempe campus only.
---

# Park & Go

Gets a student from "I'm driving to campus" to parked, with no surprise on the bill. Covers the ASU Tempe campus only.

## When to use

- "I'm driving to the MU, where should I park?"
- "How much is parking at Hayden for 3 hours?"
- "Where did I park?"
- "Remind me before parking gets more expensive."

Do not use it for permits, tickets or appeals, or for other campuses (say this Skill covers ASU Tempe only). Never say how many spaces are open: nothing here can see live availability.

## What this Skill uses

- Web: read ASU's official parking pages. If a page will not load, open it in the browser instead.
- Code sandbox: `scripts/parking_cost.py` does the exact price math and remembers the student's parking session.
- Reminders and scheduled check-ins: the "price goes up soon" texts.
- Files and media: read a photo of the spot, and keep it to send back later.
- Memory: save one line about where the student parked.

No sign-in, no keys.

## Steps

1. **Get the trip.** Find out where on campus the student is headed and how long they will stay. If the stay is missing, ask one question with a default: "How long will you be there? 2 hours?"
2. **Pick where to park.**
   - For the Memorial Union, use the Apache Boulevard Parking Structure. ASU's MU directions page recommends it: https://eoss.asu.edu/mu/about/directions
   - For any other building, search ASU's campus map and parking pages for the closest garage on the hourly list: Apache Boulevard, Fulton Center, Mill Avenue Parking Structure, Myrtle Avenue, Novus, Packard Drive, Rural Road, Stadium, Tyler Street, University Towers. Say in one short line why you picked it. If you cannot tell which is closest, name the likeliest and tell the student to check ASU's parking map.
   - For a stay of one or two hours, a cheaper hourly lot may beat a garage. Suggest one only if ASU's map shows it is near the destination. `assets/rates.json` lists the Tempe lots, their caps and time limits.
   - Never make up a garage address, and never write turn-by-turn directions. Give a Maps search link on its own line, for example `https://www.google.com/maps/search/?api=1&query=Apache+Boulevard+Parking+Structure+ASU+Tempe+AZ`. Give a walking time only if an ASU page or map supports it.
3. **Check the rates.** Read ASU's daily and hourly parking page: https://cfo.asu.edu/daily-and-hourly. The bundled rates in `assets/rates.json` were copied from it on 2026-10-24. If the live page shows different numbers, pass them to the script with `--tiers`, `--max`, `--hourly` or `--limit-min`, and mention that ASU's page shows new rates. If you cannot read the page, use the bundled rates and say they are from October 24.
4. **Work out the cost.** Run from this Skill's folder, with the stay in minutes:

   ```bash
   python3 scripts/parking_cost.py cost --minutes <minutes>
   python3 scripts/parking_cost.py cost --minutes <minutes> --lot "Lot 9"
   ```

   The first line to use is `Cost:`. Garage prices are exact. Lot prices are estimates because ASU does not say how part hours are billed; say "about". If the output says OVER, tell the student the lot has a time limit they would pass.
5. **Reply** following the Replies section below.
6. **Offer price alerts.** After the reply, ask once: "Want a text 10 minutes before the price goes up?" If the student says yes, run:

   ```bash
   python3 scripts/parking_cost.py reminders --start <local YYYY-MM-DDTHH:MM> --stay <minutes>
   ```

   Add `--lot "<Lot N>"` for a lot. Each output line is `time | message`. Create one scheduled check-in per line at that time, using the message as the text, with "Park & Go:" in front so it makes sense when it arrives later. Confirm the times in one short line. The student can ask for a different lead time (`--lead 15`).
7. **Remember the spot.** Ask the student to send a photo of the level or section, or to say where they parked. Read any level, section or pillar sign in the photo. Then run:

   ```bash
   python3 scripts/parking_cost.py save --name "<garage or lot>" --start <local YYYY-MM-DDTHH:MM> --note "<level, section, landmark>"
   ```

   Add the same rate options you used for the cost. Keep the photo, and save one line in memory: where, what level, and when.
8. **When the student asks where their car is,** run `python3 scripts/parking_cost.py status --now <local YYYY-MM-DDTHH:MM>`. Reply with the place, the note, and what it costs so far, and send the saved photo if you kept one.
9. **When the student says they are leaving or have left,** run `python3 scripts/parking_cost.py clear`, cancel any Park & Go reminders still scheduled, and say so in one line.

Use the student's local date and time for every `--start` and `--now`. ASU Tempe is on Arizona time, which does not change for daylight saving.

## Paying

Cubbie never pays. At a garage the student pulls a ticket and pays at the exit machine, which takes Visa and MasterCard. Lots use ParkMobile or AMP Park as posted. If the student wants help with an app or a reservation page, hand them the browser for the payment step. ASU's page says weekend visitors must pull a ticket and pay, so parking is not free on Saturday or Sunday. It also says availability depends on campus events and construction.

## Replies

Short, plain text, one idea per message, no Markdown. Lead with where to park. Put links on their own line. Example:

```text
Park at the Apache Boulevard garage.
2 hours is $8.

https://www.google.com/maps/search/?api=1&query=Apache+Boulevard+Parking+Structure+ASU+Tempe+AZ

Want a text 10 min before the price goes up?
```

When you cannot confirm something (a rate you could not read, a garage you could not match to the building), say so in one line instead of guessing.

## When something fails

| What happened | What to do |
| --- | --- |
| Script exit code 2 | The input was wrong. Fix it and run once more. For an unknown lot, read its rate and cap from ASU's page and pass `--hourly` and `--max` |
| Script exit code 3 (nothing saved) | Say you have no parking saved. Ask where they parked, and offer to save it |
| ASU's rates page will not load | Try the browser. If that fails too, use the bundled rates and say they are from October 24, so the student should check the posted signs |
| Destination is not on ASU Tempe | Say this Skill covers ASU Tempe only |
| Cannot tell which garage is closest | Name the likeliest one and point to ASU's parking map |
| Student asks for open spaces right now | Say you cannot see live availability, and suggest a second garage as a backup |
| No photo available later | Use the saved note from `status`. If that is empty too, say you do not have the spot saved |

Never guess a price. If the script fails twice, say you cannot work out the cost right now and give ASU's rates page link.
