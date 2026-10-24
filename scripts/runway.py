#!/usr/bin/env python3
"""Exact money math for Runway + Future Fund: goal checks, purchase trade-offs and a daily safe-to-spend number.

Every figure Cubbie texts comes from this script, so numbers never drift between conversations. The student's
numbers are saved under HOME (~/.config/runway-future-fund/state.json), which survives sandbox restarts and Skill
updates. Nothing is sent anywhere and no account is touched.

Cubbie passes the student's local date as --today (the sandbox clock may be in another time zone).
Add --sample to any command to use the bundled demo numbers in assets/sample.json; sample runs never read or
write the student's saved state.

Exit codes: 0 ok, 2 bad or missing input, 3 date problem, 4 no saved goal, 5 saved state unreadable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent.parent / "assets" / "sample.json"
MAX_MONTHS = 1200  # 100 years: anything slower counts as "never"


class Problem(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- numbers


def money(text, label: str = "amount") -> Decimal:
    """'$1,500' or '1500.50' -> Decimal. Rejects anything else."""
    try:
        value = Decimal(str(text).strip().replace("$", "").replace(",", ""))
    except InvalidOperation:
        raise Problem(f"{label} must be a number, got {text!r}.") from None
    if not value.is_finite():
        raise Problem(f"{label} must be a number, got {text!r}.")
    return value


def dollars(value: Decimal) -> str:
    """$1,500 for whole amounts, $12.50 otherwise."""
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value == value.to_integral_value():
        return f"${int(value):,}"
    return f"${value:,.2f}"


def whole_months(value: Decimal) -> str:
    """42 -> '42', 43.2 -> '43.2' (one decimal, never a fake-precise tail)."""
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return str(int(rounded)) if rounded == rounded.to_integral_value() else str(rounded)


def plural(value: Decimal) -> str:
    return "month" if whole_months(value) == "1" else "months"


def parse_day(text: str, label: str) -> date:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise Problem(f"{label} must look like 2026-11-07, got {text!r}.", 3) from None


def add_months(start: date, months: int) -> date:
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    last = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(start.day, last))


def months_between(start: date, end: date) -> Decimal:
    """Whole calendar months from start to end, plus the leftover days as a fraction of 30."""
    if end <= start:
        return Decimal(0)
    whole = (end.year - start.year) * 12 + end.month - start.month
    if add_months(start, whole) > end:
        whole -= 1
    leftover = (end - add_months(start, whole)).days
    return Decimal(whole) + Decimal(leftover) / Decimal(30)


# ---------------------------------------------------------------- the math


def months_to_goal(target: Decimal, saved: Decimal, monthly: Decimal, rate: Decimal = Decimal(0),
                   spends: tuple = ()) -> Decimal | None:
    """Months until the pot reaches target. rate is a yearly percent (0 by default).

    spends is a list of (month, amount) taken out of the pot at the start of that month (0 = today).
    Returns None when the goal is not reached within 100 years.
    """
    pot, monthly_rate = saved, rate / Decimal(1200)
    for month in range(MAX_MONTHS + 1):
        for when, amount in spends:
            if when == month:
                pot -= amount
        if pot >= target:
            return Decimal(month)
        before = pot
        pot = pot * (1 + monthly_rate) + monthly
        if pot >= target:
            return Decimal(month) + (target - before) / (pot - before)
    return None


def monthly_needed(target: Decimal, saved: Decimal, months: Decimal) -> Decimal:
    """Monthly amount that lands on target in `months`, rounded up to whole dollars (no interest)."""
    if months <= 0:
        raise Problem("The deadline has to be in the future.", 3)
    return ((target - saved) / months).to_integral_value(rounding=ROUND_CEILING)


def daily_number(balance: Decimal, bills: Decimal, buffer: Decimal, reserve: Decimal, days: int) -> Decimal:
    """(balance - bills - buffer - reserve) / days, rounded down to whole dollars. Negative means a shortfall."""
    if days < 1:
        raise Problem("Payday has to be after today.", 3)
    return ((balance - bills - buffer - reserve) / Decimal(days)).to_integral_value(rounding=ROUND_FLOOR)


# ---------------------------------------------------------------- saved state


def state_file() -> Path:
    # RUNWAY_DATA_DIR lets tests and other agents keep state somewhere else.
    base = os.environ.get("RUNWAY_DATA_DIR") or Path.home() / ".config" / "runway-future-fund"
    return Path(base) / "state.json"


def load_state(sample: bool) -> dict:
    path = SAMPLE if sample else state_file()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise Problem("The saved numbers could not be read. Ask the student to give their numbers again.", 5) from None
    return data if isinstance(data, dict) else {}


def save_state(state: dict, sample: bool) -> None:
    if sample:
        return
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def bill_total(state: dict) -> Decimal:
    return sum((money(b["amount"], "bill") for b in state.get("bills", [])), Decimal(0))


def need(state: dict, key: str, flag: str, value):
    """Prefer the flag; else the saved value; else tell Cubbie exactly what to ask."""
    if value is not None:
        return value
    if state.get(key) not in (None, ""):
        return state[key]
    raise Problem(f"Missing {key}. Ask the student for it (or pass {flag}).")


def goal_numbers(state: dict, args) -> tuple:
    """(target, saved, monthly, rate) from flags, falling back to the saved goal."""
    saved_goal = state.get("goal") or {}

    def pick(flag_value, key, label):
        raw = flag_value if flag_value is not None else saved_goal.get(key)
        if raw in (None, ""):
            raise Problem(f"No goal {label} yet. Ask the student for their goal first.", 4)
        return money(raw, label)

    rate = getattr(args, "rate", None)
    rate = money(rate if rate is not None else saved_goal.get("rate", "0"), "interest rate")
    if rate < 0:
        raise Problem("interest rate cannot be negative.")
    return pick(getattr(args, "target", None), "target", "target"), pick(getattr(args, "saved", None), "saved", "saved amount"), \
        pick(getattr(args, "monthly", None), "monthly", "monthly amount"), rate


def say_rate(rate: Decimal) -> str:
    return f" (assuming {rate.normalize():f}% a year)" if rate else ""


# ---------------------------------------------------------------- commands


def cmd_set(args, state: dict, sample: bool) -> list[str]:
    if args.balance is not None:
        state["balance"] = str(money(args.balance, "balance"))
    if args.payday is not None:
        state["payday"] = parse_day(args.payday, "payday").isoformat()
    if args.buffer is not None:
        state["buffer"] = str(money(args.buffer, "buffer"))
    if args.bill is not None:
        state["bills"] = [parse_bill(item) for item in args.bill]
    for item in args.add_bill or []:
        bill = parse_bill(item)
        state["bills"] = [b for b in state.get("bills", []) if b["name"].lower() != bill["name"].lower()] + [bill]
    for name in args.remove_bill or []:
        state["bills"] = [b for b in state.get("bills", []) if b["name"].lower() != name.lower()]
    goal = state.setdefault("goal", {})
    for flag, key in (("goal_target", "target"), ("goal_saved", "saved"), ("goal_monthly", "monthly"), ("goal_rate", "rate")):
        value = getattr(args, flag)
        if value is not None:
            goal[key] = str(money(value, key))
    if args.goal_name:
        goal["name"] = args.goal_name.strip()
    if args.goal_months is not None:
        goal["deadline"] = add_months(parse_day(need({}, "today", "--today", args.today), "today"), args.goal_months).isoformat()
    if not goal:
        state.pop("goal")
    save_state(state, sample)
    note = "Sample run: nothing saved." if sample else "Saved."
    return [note, *summary_lines(state)]


def parse_bill(item: str) -> dict:
    name, sep, amount = item.rpartition(":")
    if not sep or not name.strip():
        raise Problem(f"A bill looks like 'Phone:45', got {item!r}.")
    return {"name": name.strip(), "amount": str(money(amount, f"{name.strip()} bill"))}


def summary_lines(state: dict) -> list[str]:
    lines = []
    if "balance" in state:
        lines.append(f"Balance {dollars(money(state['balance']))}")
    if "payday" in state:
        lines.append(f"Payday {state['payday']}")
    if state.get("bills"):
        listing = ", ".join(f"{b['name']} {dollars(money(b['amount']))}" for b in state["bills"])
        lines.append(f"Bills before payday: {listing} (total {dollars(bill_total(state))})")
    if "buffer" in state:
        lines.append(f"Buffer {dollars(money(state['buffer']))}")
    goal = state.get("goal") or {}
    if goal:
        parts = [f"{key} {goal[key]}" for key in ("target", "saved", "monthly", "deadline") if key in goal]
        lines.append(f"Goal {goal.get('name', '')}: {', '.join(parts)}".replace("Goal :", "Goal:"))
    return lines or ["Nothing saved yet."]


def cmd_show(args, state: dict, sample: bool) -> list[str]:
    return summary_lines(state)


def cmd_goal(args, state: dict, sample: bool) -> list[str]:
    target, saved, monthly, rate = goal_numbers(state, args)
    if saved >= target:
        return [f"{dollars(saved)} saved already covers the {dollars(target)} goal."]
    lines = []
    deadline = None
    if args.months is not None:
        today = parse_day(need(state, "today", "--today", args.today), "today")
        deadline = add_months(today, args.months)
        months_left = Decimal(args.months)
    elif (state.get("goal") or {}).get("deadline") and args.target is None:
        today = parse_day(need(state, "today", "--today", args.today), "today")
        deadline = parse_day(state["goal"]["deadline"], "deadline")
        months_left = months_between(today, deadline)
    else:
        months_left = None
    pace = months_to_goal(target, saved, monthly, rate)
    if pace is None:
        lines.append(f"At {dollars(monthly)} a month the {dollars(target)} goal isn't reached.")
    else:
        lines.append(f"At {dollars(monthly)} a month, {dollars(target)} takes {whole_months(pace)} {plural(pace)}{say_rate(rate)}.")
    if months_left is not None and months_left > 0:
        projected = saved + monthly * months_left if not rate else None
        if rate:
            end_pot = saved
            for _ in range(int(months_left)):
                end_pot = end_pot * (1 + rate / Decimal(1200)) + monthly
            projected = end_pot
        gap = target - projected
        by = f"by {deadline:%b %Y}" if deadline else ""
        if gap > 0:
            lines.append(f"In {whole_months(months_left)} {plural(months_left)} that reaches {dollars(projected)}, "
                         f"{dollars(gap)} short of the goal{' ' + by if by else ''}.")
            if not rate:
                lines.append(f"Hitting it on time takes about {dollars(monthly_needed(target, saved, months_left))} a month.")
        else:
            lines.append(f"That reaches {dollars(projected)} {by}, so the goal is covered.".replace("  ", " "))
    if args.save:
        goal = state.setdefault("goal", {})
        goal.update({"target": str(target), "saved": str(saved), "monthly": str(monthly), "rate": str(rate)})
        if deadline:
            goal["deadline"] = deadline.isoformat()
        save_state(state, sample)
    return lines


def cmd_buy(args, state: dict, sample: bool) -> list[str]:
    target, saved, monthly, rate = goal_numbers(state, args)
    cost = money(args.cost, "cost")
    base = months_to_goal(target, saved, monthly, rate)
    after = months_to_goal(target, saved, monthly, rate, ((0, cost),))
    label = args.item or "That"
    if base is None or after is None:
        return [f"{label} costs {dollars(cost)}. At {dollars(monthly)} a month the goal isn't reached either way."]
    delay = after - base
    return [f"{label} costs {dollars(cost)} today.",
            f"It pushes the goal back {whole_months(delay)} {plural(delay)}, from {whole_months(base)} to {whole_months(after)}{say_rate(rate)}."]


def parse_option(text: str) -> tuple:
    """'Buy now:300:0' -> (name, cost, wait months)."""
    parts = text.rsplit(":", 2)
    if len(parts) != 3 or not parts[0].strip():
        raise Problem(f"An option looks like 'Buy now:300:0' (name, cost, months to wait), got {text!r}.")
    try:
        wait = int(parts[2])
    except ValueError:
        raise Problem(f"Months to wait must be a whole number in {text!r}.") from None
    if wait < 0:
        raise Problem(f"Months to wait can't be negative in {text!r}.")
    return parts[0].strip(), money(parts[1], f"{parts[0].strip()} cost"), wait


def cmd_compare(args, state: dict, sample: bool) -> list[str]:
    target, saved, monthly, rate = goal_numbers(state, args)
    base = months_to_goal(target, saved, monthly, rate)
    if base is None:
        return [f"At {dollars(monthly)} a month the goal isn't reached, so there's nothing to compare."]
    rows = []
    for text in args.option:
        name, cost, wait = parse_option(text)
        after = months_to_goal(target, saved, monthly, rate, ((wait, cost),))
        rows.append((name, cost, wait, None if after is None else after - base))
    lines = [f"Goal date change for each choice{say_rate(rate)}:"]
    for name, cost, wait, delay in rows:
        timing = "today" if wait == 0 else f"in {wait} {'month' if wait == 1 else 'months'}"
        effect = "never reaches the goal" if delay is None else f"+{whole_months(delay)} {plural(delay)}"
        lines.append(f"- {name}: {dollars(cost)} {timing}, {effect}")
    for name, cost, wait, delay in rows:
        twin = next((n for n, c, w, d in rows if w == 0 and c == cost and wait > 0 and d is not None and delay is not None
                     and whole_months(d) == whole_months(delay)), None)
        if twin:
            lines.append(f"{name} and {twin} land on the same date: waiting doesn't change what it costs"
                         + ("." if not rate else ", and the interest here is too small to matter."))
    return lines


def days_to_payday(state: dict, args, today_text) -> int:
    today = parse_day(need(state, "today", "--today", today_text), "today")
    payday = parse_day(need(state, "payday", "--payday", args.payday), "payday")
    days = (payday - today).days
    if days < 1:
        raise Problem("Payday has to be after today.", 3)
    return days


def daily_inputs(args, state: dict) -> tuple:
    balance = money(need(state, "balance", "--balance", args.balance), "balance")
    bills = money(args.bills, "bills") if args.bills is not None else bill_total(state)
    buffer = money(args.buffer if args.buffer is not None else state.get("buffer", "0"), "buffer")
    return balance, bills, buffer, days_to_payday(state, args, args.today)


def daily_line(value: Decimal) -> str:
    return f"{dollars(value)} a day" if value >= 0 else f"short by {dollars(-value)} a day"


def cmd_daily(args, state: dict, sample: bool) -> list[str]:
    balance, bills, buffer, days = daily_inputs(args, state)
    reserve = money(args.reserve or "0", "reserve")
    number = daily_number(balance, bills, buffer, reserve, days)
    lines = [f"Safe to spend: {daily_line(number)} for the next {days} days."]
    if number < 0:
        lines.append(f"Bills and your buffer already take {dollars(bills + buffer + reserve)} of the {dollars(balance)}.")
    else:
        lines.append(f"({dollars(balance)} - {dollars(bills)} bills - {dollars(buffer)} buffer"
                     + (f" - {dollars(reserve)} for your goal" if reserve else "") + f", split over {days} days, rounded down.)")
    return lines


def cmd_headsup(args, state: dict, sample: bool) -> list[str]:
    balance, bills, buffer, days = daily_inputs(args, state)
    cost = money(args.cost, "charge")
    before = daily_number(balance, bills, buffer, Decimal(0), days)
    after = daily_number(balance, bills + cost, buffer, Decimal(0), days)
    label = args.item or "That charge"
    return [f"{label} ({dollars(cost)}) changes your daily number from {daily_line(before)} to {daily_line(after)}."]


def cmd_refund(args, state: dict, sample: bool) -> list[str]:
    balance, bills, buffer, days = daily_inputs(args, state)
    refund = money(args.refund, "refund")
    amounts = [money(x, "goal amount") for x in (args.to_goal or "0").split(",")]
    goal = state.get("goal") or {}
    have_goal = all(goal.get(k) not in (None, "") for k in ("target", "saved", "monthly"))
    lines = [f"Refund of {dollars(refund)} stretched over {days} days until payday:"]
    for amount in amounts:
        if amount > balance + refund:
            raise Problem("The goal amount is bigger than the balance plus the refund.")
        number = daily_number(balance + refund, bills, buffer, amount, days)
        text = f"- {dollars(amount)} to your goal: {daily_line(number)}"
        if have_goal and not args.no_goal:
            target, saved, monthly, rate = goal_numbers(state, argparse.Namespace())
            months = months_to_goal(target, saved + amount, monthly, rate)
            text += "" if months is None else f", goal in {whole_months(months)} {plural(months)}"
        lines.append(text)
    return lines


def cmd_recap(args, state: dict, sample: bool) -> list[str]:
    target, saved, monthly, rate = goal_numbers(state, args)
    goal = state.get("goal") or {}
    share = (saved / target * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    lines = [f"{goal.get('name') or 'Your goal'}: {dollars(saved)} of {dollars(target)} ({share}%)."]
    pace = months_to_goal(target, saved, monthly, rate)
    if pace is not None and saved < target:
        lines.append(f"At {dollars(monthly)} a month that's {whole_months(pace)} {plural(pace)} to go{say_rate(rate)}.")
    if goal.get("deadline") and saved < target:
        today = parse_day(need(state, "today", "--today", args.today), "today")
        left = months_between(today, parse_day(goal["deadline"], "deadline"))
        if left > 0 and not rate:
            lines.append(f"To finish by {parse_day(goal['deadline'], 'deadline'):%b %Y} takes about "
                         f"{dollars(monthly_needed(target, saved, left))} a month.")
    return lines


def cmd_tempted(args, state: dict, sample: bool) -> list[str]:
    items = state.setdefault("tempted", [])
    if args.action == "add":
        if not args.item:
            raise Problem("Tell me what the student is tempted by (--item).")
        cost = money(args.cost, "cost") if args.cost is not None else None
        now = need({}, "now", "--now", args.now)
        try:
            start = datetime.strptime(now.strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            raise Problem(f"--now must look like 2026-10-24T15:44 (the student's local time), got {now!r}.", 3) from None
        check = start + timedelta(hours=48)
        items.append({"item": args.item.strip(), "cost": None if cost is None else str(cost), "check_at": check.strftime("%Y-%m-%dT%H:%M")})
        save_state(state, sample)
        return [f"Logged {args.item.strip()}. Check back {check:%a %b %d at %I:%M %p}.".replace(" 0", " ")]
    if args.action == "clear":
        keep = [i for i in items if i["item"].lower() != (args.item or "").lower()]
        if len(keep) == len(items):
            raise Problem("Nothing logged with that name.")
        state["tempted"] = keep
        save_state(state, sample)
        return [f"Cleared {args.item.strip()}."]
    if not items:
        return ["Nothing logged."]
    return [f"- {i['item']}" + (f" ({dollars(money(i['cost']))})" if i.get("cost") else "") + f", check back {i['check_at']}" for i in items]


# ---------------------------------------------------------------- command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
        p.add_argument("--sample", action="store_true", help="use assets/sample.json and never touch saved state")
        p.add_argument("--today", help="the student's local date, YYYY-MM-DD")
        return p

    def goal_flags(p):
        p.add_argument("--target", help="goal amount")
        p.add_argument("--saved", help="amount saved so far")
        p.add_argument("--monthly", help="amount put away each month")
        p.add_argument("--rate", help="optional yearly interest percent, default 0")

    def cash_flags(p):
        p.add_argument("--balance")
        p.add_argument("--payday", help="next payday, YYYY-MM-DD")
        p.add_argument("--bills", help="total of bills due before payday (default: the saved bills)")
        p.add_argument("--buffer", help="cushion to keep untouched (default: the saved buffer, else 0)")

    p = add("set", cmd_set, "save the student's numbers")
    p.add_argument("--balance")
    p.add_argument("--payday")
    p.add_argument("--buffer")
    p.add_argument("--bill", action="append", help="replace all bills; repeat as 'Phone:45'")
    p.add_argument("--add-bill", action="append", help="add or update one bill, 'Phone:45'")
    p.add_argument("--remove-bill", action="append", help="remove a bill by name")
    p.add_argument("--goal-name")
    p.add_argument("--goal-target")
    p.add_argument("--goal-saved")
    p.add_argument("--goal-monthly")
    p.add_argument("--goal-rate")
    p.add_argument("--goal-months", type=int, help="months from --today until the goal date")

    add("show", cmd_show, "print what is saved")

    p = add("goal", cmd_goal, "does the monthly amount reach the goal in time?")
    goal_flags(p)
    p.add_argument("--months", type=int, help="months the student wants to reach it in")
    p.add_argument("--save", action="store_true", help="save these numbers as the goal")

    p = add("buy", cmd_buy, "how far does one purchase push the goal back?")
    goal_flags(p)
    p.add_argument("--cost", required=True)
    p.add_argument("--item")

    p = add("compare", cmd_compare, "compare purchase choices by goal date")
    goal_flags(p)
    p.add_argument("--option", action="append", required=True, help="'Buy now:300:0' = name:cost:months to wait")

    p = add("daily", cmd_daily, "the safe-to-spend number for today")
    cash_flags(p)
    p.add_argument("--reserve", help="amount set aside for the goal this pay period")

    p = add("headsup", cmd_headsup, "how a bill or charge changes the daily number")
    cash_flags(p)
    p.add_argument("--cost", required=True)
    p.add_argument("--item")

    p = add("refund", cmd_refund, "stretch a refund to payday, with goal options")
    cash_flags(p)
    p.add_argument("--refund", required=True)
    p.add_argument("--to-goal", help="comma-separated amounts to put toward the goal, e.g. 0,200,400")
    p.add_argument("--no-goal", action="store_true", help="leave out goal dates")

    p = add("recap", cmd_recap, "goal progress for the weekly text")
    goal_flags(p)

    p = add("tempted", cmd_tempted, "log something the student is tempted by, to ask again in 48 hours")
    p.add_argument("action", choices=["add", "list", "clear"])
    p.add_argument("--item")
    p.add_argument("--cost")
    p.add_argument("--now", help="student's local time, YYYY-MM-DDTHH:MM")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        state = load_state(args.sample)
        lines = args.func(args, state, args.sample)
    except Problem as problem:
        print(problem, file=sys.stderr)
        return problem.code
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
