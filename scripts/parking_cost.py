#!/usr/bin/env python3
"""Parking cost and price-step reminders for ASU Tempe hourly parking.

Rates come from assets/rates.json (copied from ASU Parking and Transportation Services'
daily and hourly page). Cubbie reads the live ASU page first and passes any differences with
--tiers, --max, --hourly and --limit-min, so a rate change needs no code change.

The script never reads the clock: Cubbie passes the student's local date and time
(--start, --now) as "YYYY-MM-DDTHH:MM", because the sandbox clock may be in another time zone.
The student's current parking session is saved under HOME (~/.config/park-and-go), which
survives sandbox restarts and Skill updates. --sample leaves that saved state alone.

Commands:
  cost       --minutes N [rate options]            price for a stay and the next price step
  reminders  --start T [--stay N] [--lead N]       when to text the student before each price step
  save       --name X --start T [--note X]         remember where and when the student parked
  status     --now T                               what the student owes so far and where the car is
  clear                                            forget the saved session

Exit codes: 0 ok, 2 bad arguments, 3 nothing saved.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

RATES_FILE = Path(__file__).resolve().parent.parent / "assets" / "rates.json"


def fail(message: str, code: int):
    print(message, file=sys.stderr)
    sys.exit(code)


def load_rates() -> dict:
    try:
        return json.loads(RATES_FILE.read_text())
    except (OSError, ValueError):
        fail("assets/rates.json is missing or unreadable.", 2)


def session_file() -> Path:
    data_dir = os.environ.get("SKILL_DATA_DIR") or Path.home() / ".config" / "park-and-go"
    return Path(data_dir) / "session.json"


def money(value: float) -> str:
    return f"${int(value)}" if float(value).is_integer() else f"${value:.2f}"


def clock(moment: datetime) -> str:
    return f"{moment.hour % 12 or 12}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"


def duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    return f"{hours}h" if hours else f"{rest}m"


def parse_time(text: str) -> datetime:
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        fail(f"Bad time '{text}'. Use the student's local time as YYYY-MM-DDTHH:MM.", 2)
    return moment.replace(tzinfo=None)


def parse_tiers(text: str) -> list[list[float]]:
    try:
        tiers = [[int(a), float(b)] for a, b in (part.split(":") for part in text.split(","))]
    except ValueError:
        fail("Bad --tiers. Use minutes:price pairs, for example 60:4,120:8,180:12,240:16.", 2)
    if not tiers or any(tiers[i][0] >= tiers[i + 1][0] for i in range(len(tiers) - 1)):
        fail("--tiers must be in increasing order of minutes.", 2)
    return tiers


def build_spec(args: argparse.Namespace, rates: dict) -> dict:
    """The pricing rule for one place: a garage with price tiers, or a lot with an hourly rate."""
    if args.lot:
        key = args.lot.strip().lower()
        base = rates["lots"]["named"].get(key)
        if base is None:
            if args.hourly is None or args.max is None:
                fail(f"Unknown lot '{args.lot}'. Pass --hourly and --max from ASU's page.", 2)
            base = {"hourly": args.hourly, "max": args.max, "limit_min": None}
        return {
            "kind": "lot",
            "name": args.lot.strip(),
            "hourly": args.hourly if args.hourly is not None else base["hourly"],
            "max": args.max if args.max is not None else base["max"],
            "limit_min": args.limit_min if args.limit_min is not None else base.get("limit_min"),
        }
    garage = rates["garage"]
    return {
        "kind": "garage",
        "name": "garage",
        "tiers": parse_tiers(args.tiers) if args.tiers else garage["tiers"],
        "max": args.max if args.max is not None else garage["max"],
        "limit_min": args.limit_min,
    }


def price(minutes: int, spec: dict) -> float:
    """Price for a stay of this many minutes. A stay at exactly a tier limit still costs that tier."""
    if spec["kind"] == "garage":
        for limit, amount in spec["tiers"]:
            if minutes <= limit:
                return min(amount, spec["max"])
        return spec["max"]
    hours = max(1, math.ceil(minutes / 60))
    return min(spec["max"], spec["hourly"] * hours)


def price_steps(spec: dict, horizon: int = 720) -> list[tuple[int, float, float]]:
    """(minute, old price, new price): the price rises once the stay goes past that minute."""
    if spec["kind"] == "garage":
        marks = [int(limit) for limit, _ in spec["tiers"]]
    else:
        marks = list(range(60, horizon + 1, 60))
    steps = []
    for mark in marks:
        old, new = price(mark, spec), price(mark + 1, spec)
        if new > old:
            steps.append((mark, old, new))
    return steps


def next_step(minutes: int, spec: dict):
    for mark, old, new in price_steps(spec):
        if mark >= minutes:
            return mark, new
    return None


def next_step_line(minutes: int, spec: dict) -> str:
    step = next_step(minutes, spec)
    if step:
        return f"Next step: {money(step[1])} after {step[0]} min"
    return f"Next step: none (max {money(spec['max'])})"


def cmd_cost(args: argparse.Namespace, spec: dict) -> None:
    if args.minutes <= 0:
        fail("--minutes must be more than 0.", 2)
    print(f"Stay: {args.minutes} min ({duration(args.minutes)})")
    print(f"Cost: {money(price(args.minutes, spec))}" + (" (estimate)" if spec["kind"] == "lot" else ""))
    print(next_step_line(args.minutes, spec))
    if spec["kind"] == "lot":
        print("Lot billing for part hours is not stated by ASU; counted as a full hour.")
    if spec.get("limit_min"):
        over = args.minutes - spec["limit_min"]
        print(f"Time limit: {spec['limit_min']} min" + (f" - OVER by {over} min" if over > 0 else ""))


def cmd_reminders(args: argparse.Namespace, spec: dict) -> None:
    start = parse_time(args.start)
    events = []
    for mark, old, new in price_steps(spec):
        if args.stay and mark >= args.stay:
            continue
        when = start + timedelta(minutes=mark)
        message = (f"Price steps from {money(old)} to {money(new)} at {clock(when)}. "
                   f"Leave by then to pay {money(old)}.")
        events.append((mark, message))
    limit = spec.get("limit_min")
    if limit and (not args.stay or limit <= args.stay):
        when = start + timedelta(minutes=limit)
        events.append((limit, f"Time limit ends at {clock(when)}. Move your car by then."))
    reminders = [(m - args.lead, text) for m, text in sorted(events) if m - args.lead > 0]
    if not reminders:
        print("No price changes during the stay. No reminders needed.")
        return
    for minute, text in reminders:
        print(f"{(start + timedelta(minutes=minute)).strftime('%Y-%m-%dT%H:%M')} | {text}")


def cmd_save(args: argparse.Namespace, spec: dict) -> None:
    start = parse_time(args.start)
    path = session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    spec["name"] = args.name
    path.write_text(json.dumps({"name": args.name, "start": start.strftime("%Y-%m-%dT%H:%M"),
                                "note": args.note or "", "spec": spec}))
    note = f" Note: {args.note}." if args.note else ""
    print(f"Saved: {args.name}, parked at {clock(start)}.{note}")


def cmd_status(args: argparse.Namespace) -> None:
    try:
        saved = json.loads(session_file().read_text())
    except (OSError, ValueError):
        fail("Nothing saved. Ask the student where they parked.", 3)
    spec = saved["spec"]
    start = parse_time(saved["start"])
    elapsed = max(0, int((parse_time(args.now) - start).total_seconds() // 60))
    spot = f" ({saved['note']})" if saved.get("note") else ""
    print(f"Parked: {saved['name']}{spot}")
    print(f"Since: {clock(start)} ({duration(elapsed)} ago)")
    print(f"Cost so far: {money(price(max(elapsed, 1), spec))}")
    step = next_step(elapsed, spec)
    if step:
        print(f"Next step: {money(step[1])} after {step[0]} min (at {clock(start + timedelta(minutes=step[0]))})")
    else:
        print(f"Next step: none (max {money(spec['max'])})")
    if spec.get("limit_min") and elapsed > spec["limit_min"]:
        print(f"Time limit of {spec['limit_min']} min passed {elapsed - spec['limit_min']} min ago.")


def cmd_clear() -> None:
    try:
        session_file().unlink()
        print("Cleared the saved parking session.")
    except OSError:
        print("Nothing was saved.")


def run_sample() -> None:
    rates = load_rates()
    args = argparse.Namespace(lot=None, tiers=None, max=None, hourly=None, limit_min=None)
    spec = build_spec(args, rates)
    print(f"Sample using bundled ASU rates as of {rates['as_of']}. Nothing is saved.")
    for minutes in (30, 90, 210, 300):
        print(f"{minutes} min -> {money(price(minutes, spec))}")
    sample = argparse.Namespace(start="2026-10-24T14:30", stay=150, lead=10)
    print("Reminders for a 150 min stay starting 2026-10-24T14:30:")
    cmd_reminders(sample, spec)


def build_parser() -> argparse.ArgumentParser:
    rate_options = argparse.ArgumentParser(add_help=False)
    rate_options.add_argument("--lot", help='A Tempe lot such as "Lot 9". Leave out for a garage.')
    rate_options.add_argument("--tiers", help="Garage tiers from ASU's page, minutes:price pairs, e.g. 60:4,120:8")
    rate_options.add_argument("--max", type=float, help="Maximum rate from ASU's page")
    rate_options.add_argument("--hourly", type=float, help="Lot hourly rate from ASU's page")
    rate_options.add_argument("--limit-min", type=int, help="Lot time limit in minutes")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="Show a demo with bundled rates; saves nothing")
    commands = parser.add_subparsers(dest="command")

    cost = commands.add_parser("cost", parents=[rate_options])
    cost.add_argument("--minutes", type=int, required=True)

    remind = commands.add_parser("reminders", parents=[rate_options])
    remind.add_argument("--start", required=True, help="When the student parked, local YYYY-MM-DDTHH:MM")
    remind.add_argument("--stay", type=int, help="Planned stay in minutes; skips price steps after it")
    remind.add_argument("--lead", type=int, default=10, help="Minutes before each step to text the student")

    save = commands.add_parser("save", parents=[rate_options])
    save.add_argument("--name", required=True, help="Where the student parked, e.g. Apache Boulevard garage")
    save.add_argument("--start", required=True, help="When the student parked, local YYYY-MM-DDTHH:MM")
    save.add_argument("--note", help="Level, section or landmark")

    status = commands.add_parser("status")
    status.add_argument("--now", required=True, help="The student's local time, YYYY-MM-DDTHH:MM")

    commands.add_parser("clear")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.sample:
        run_sample()
        return
    if args.command is None:
        parser.error("choose a command, or use --sample")
    if args.command == "status":
        cmd_status(args)
    elif args.command == "clear":
        cmd_clear()
    else:
        spec = build_spec(args, load_rates())
        {"cost": cmd_cost, "reminders": cmd_reminders, "save": cmd_save}[args.command](args, spec)


if __name__ == "__main__":
    main()
