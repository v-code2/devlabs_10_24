"""Unit tests for scripts/runway.py. Run from the Skill folder: python3 -m unittest discover -s tests"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import runway  # noqa: E402

D = Decimal


def run(*argv, data_dir=None):
    out, err = io.StringIO(), io.StringIO()
    old = os.environ.get("RUNWAY_DATA_DIR")
    os.environ["RUNWAY_DATA_DIR"] = data_dir or tempfile.mkdtemp()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runway.main(list(argv))
    finally:
        if old is None:
            os.environ.pop("RUNWAY_DATA_DIR", None)
        else:
            os.environ["RUNWAY_DATA_DIR"] = old
    return code, out.getvalue(), err.getvalue()


GOAL = ("--target", "12000", "--saved", "1500", "--monthly", "250")


class GoalMath(unittest.TestCase):
    def test_demo_goal_takes_42_months(self):
        self.assertEqual(runway.months_to_goal(D(12000), D(1500), D(250)), D(42))

    def test_demo_needs_292_a_month_for_36(self):
        self.assertEqual(runway.monthly_needed(D(12000), D(1500), D(36)), D(292))

    def test_ticket_delays_1_2_months(self):
        base = runway.months_to_goal(D(12000), D(1500), D(250))
        after = runway.months_to_goal(D(12000), D(1500), D(250), spends=((0, D(300)),))
        self.assertEqual(round(after - base, 1), D("1.2"))

    def test_alternative_delays_0_4_months(self):
        base = runway.months_to_goal(D(12000), D(1500), D(250))
        after = runway.months_to_goal(D(12000), D(1500), D(250), spends=((0, D(100)),))
        self.assertEqual(round(after - base, 1), D("0.4"))

    def test_waiting_changes_nothing_at_zero_interest(self):
        now = runway.months_to_goal(D(12000), D(1500), D(250), spends=((0, D(300)),))
        later = runway.months_to_goal(D(12000), D(1500), D(250), spends=((2, D(300)),))
        self.assertEqual(now, later)

    def test_waiting_helps_a_little_with_interest(self):
        now = runway.months_to_goal(D(12000), D(1500), D(250), D(4), ((0, D(300)),))
        later = runway.months_to_goal(D(12000), D(1500), D(250), D(4), ((2, D(300)),))
        self.assertLess(later, now)

    def test_no_progress_never_reaches(self):
        self.assertIsNone(runway.months_to_goal(D(1000), D(0), D(0)))

    def test_already_there_is_zero(self):
        self.assertEqual(runway.months_to_goal(D(1000), D(1000), D(10)), D(0))

    def test_deadline_must_be_future(self):
        with self.assertRaises(runway.Problem):
            runway.monthly_needed(D(100), D(0), D(0))


class DailyNumber(unittest.TestCase):
    def test_rounds_down(self):
        # 420 - 60 - 40 = 320 over 12 days = 26.67 -> 26
        self.assertEqual(runway.daily_number(D(420), D(60), D(40), D(0), 12), D(26))

    def test_exact_division(self):
        self.assertEqual(runway.daily_number(D(300), D(0), D(0), D(0), 10), D(30))

    def test_goal_reserve_lowers_it(self):
        self.assertEqual(runway.daily_number(D(420), D(60), D(40), D(100), 10), D(22))

    def test_shortfall_is_negative(self):
        self.assertLess(runway.daily_number(D(50), D(100), D(0), D(0), 5), 0)

    def test_payday_today_is_rejected(self):
        with self.assertRaises(runway.Problem):
            runway.daily_number(D(100), D(0), D(0), D(0), 0)


class Helpers(unittest.TestCase):
    def test_money_parsing(self):
        self.assertEqual(runway.money("$1,500.50"), D("1500.50"))
        with self.assertRaises(runway.Problem):
            runway.money("lots")
        with self.assertRaises(runway.Problem):
            runway.money("NaN")

    def test_dollar_format(self):
        self.assertEqual(runway.dollars(D(12000)), "$12,000")
        self.assertEqual(runway.dollars(D("12.5")), "$12.50")

    def test_month_format(self):
        self.assertEqual(runway.whole_months(D(42)), "42")
        self.assertEqual(runway.whole_months(D("43.2000001")), "43.2")

    def test_add_months_clamps_day(self):
        self.assertEqual(runway.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(runway.add_months(date(2026, 10, 24), 36), date(2029, 10, 24))

    def test_months_between(self):
        self.assertEqual(runway.months_between(date(2026, 10, 24), date(2029, 10, 24)), D(36))


class CommandLine(unittest.TestCase):
    def test_goal_command_matches_demo(self):
        code, out, _ = run("goal", *GOAL, "--months", "36", "--today", "2026-10-24")
        self.assertEqual(code, 0)
        self.assertIn("takes 42 months", out)
        self.assertIn("$1,500 short", out)
        self.assertIn("about $292 a month", out)

    def test_buy_command(self):
        code, out, _ = run("buy", *GOAL, "--cost", "300")
        self.assertEqual(code, 0)
        self.assertIn("1.2 months", out)
        self.assertIn("from 42 to 43.2", out)

    def test_compare_command(self):
        code, out, _ = run("compare", *GOAL, "--option", "Buy now:300:0", "--option", "Wait 2 months:300:2",
                           "--option", "Cheaper:100:0")
        self.assertEqual(code, 0)
        self.assertIn("Buy now: $300 today, +1.2 months", out)
        self.assertIn("Cheaper: $100 today, +0.4 months", out)
        self.assertIn("land on the same date", out)

    def test_bad_option_is_exit_2(self):
        code, _, err = run("compare", *GOAL, "--option", "oops")
        self.assertEqual(code, 2)
        self.assertIn("name, cost", err)

    def test_set_then_daily_uses_saved_numbers(self):
        folder = tempfile.mkdtemp()
        code, out, _ = run("set", "--balance", "500", "--payday", "2026-11-07", "--bill", "Phone:45",
                           "--bill", "Rent:100", "--buffer", "30", data_dir=folder)
        self.assertEqual(code, 0)
        code, out, _ = run("daily", "--today", "2026-10-24", data_dir=folder)
        self.assertEqual(code, 0)
        self.assertIn("$23 a day for the next 14 days", out)  # (500-145-30)/14 = 23.2

    def test_add_and_remove_bill(self):
        folder = tempfile.mkdtemp()
        run("set", "--bill", "Phone:45", data_dir=folder)
        run("set", "--add-bill", "Gym:20", "--add-bill", "phone:50", data_dir=folder)
        _, out, _ = run("show", data_dir=folder)
        self.assertIn("Gym $20", out)
        self.assertIn("phone $50", out)
        self.assertNotIn("Phone $45", out)
        run("set", "--remove-bill", "gym", data_dir=folder)
        _, out, _ = run("show", data_dir=folder)
        self.assertNotIn("Gym", out)

    def test_goal_save_then_buy_without_flags(self):
        folder = tempfile.mkdtemp()
        run("goal", *GOAL, "--save", data_dir=folder)
        code, out, _ = run("buy", "--cost", "300", data_dir=folder)
        self.assertEqual(code, 0)
        self.assertIn("43.2", out)

    def test_no_goal_is_exit_4(self):
        code, _, err = run("buy", "--cost", "300")
        self.assertEqual(code, 4)
        self.assertIn("goal", err)

    def test_payday_not_after_today_is_exit_3(self):
        code, _, _ = run("daily", "--balance", "100", "--payday", "2026-10-24", "--today", "2026-10-24")
        self.assertEqual(code, 3)

    def test_bad_date_is_exit_3(self):
        code, _, err = run("daily", "--balance", "100", "--payday", "Nov 7", "--today", "2026-10-24")
        self.assertEqual(code, 3)
        self.assertIn("2026-11-07", err)

    def test_missing_balance_is_exit_2(self):
        code, _, err = run("daily", "--payday", "2026-11-07", "--today", "2026-10-24")
        self.assertEqual(code, 2)
        self.assertIn("balance", err)

    def test_shortfall_wording(self):
        code, out, _ = run("daily", "--balance", "50", "--bills", "100", "--payday", "2026-10-29", "--today", "2026-10-24")
        self.assertEqual(code, 0)
        self.assertIn("short by $10 a day", out)

    def test_headsup(self):
        code, out, _ = run("headsup", "--balance", "420", "--bills", "60", "--buffer", "40", "--payday", "2026-11-07",
                           "--today", "2026-10-24", "--cost", "40", "--item", "Textbook")
        self.assertEqual(code, 0)
        self.assertIn("from $22 a day to $20 a day", out)

    def test_refund_options(self):
        code, out, _ = run("refund", "--sample", "--today", "2026-10-24", "--refund", "900", "--to-goal", "0,200")
        self.assertEqual(code, 0)
        self.assertIn("$0 to your goal: $87 a day", out)
        self.assertIn("$200 to your goal: $72 a day", out)

    def test_refund_goal_bigger_than_money_is_rejected(self):
        code, _, _ = run("refund", "--sample", "--today", "2026-10-24", "--refund", "100", "--to-goal", "9999")
        self.assertEqual(code, 2)

    def test_recap(self):
        code, out, _ = run("recap", "--sample", "--today", "2026-10-24")
        self.assertEqual(code, 0)
        self.assertIn("13%", out)

    def test_tempted_logs_48_hours_later(self):
        folder = tempfile.mkdtemp()
        code, out, _ = run("tempted", "add", "--item", "Shoes", "--cost", "120", "--now", "2026-10-24T15:44", data_dir=folder)
        self.assertEqual(code, 0)
        self.assertIn("Mon Oct 26 at 3:44 PM", out)
        _, out, _ = run("tempted", "list", data_dir=folder)
        self.assertIn("Shoes ($120)", out)
        run("tempted", "clear", "--item", "shoes", data_dir=folder)
        _, out, _ = run("tempted", "list", data_dir=folder)
        self.assertIn("Nothing logged", out)

    def test_sample_never_writes_state(self):
        folder = tempfile.mkdtemp()
        run("set", "--sample", "--balance", "999", data_dir=folder)
        run("goal", "--sample", "--save", data_dir=folder)
        self.assertEqual(list(Path(folder).iterdir()), [])

    def test_unreadable_state_is_exit_5(self):
        folder = tempfile.mkdtemp()
        (Path(folder) / "state.json").write_text("not json")
        code, _, _ = run("show", data_dir=folder)
        self.assertEqual(code, 5)

    def test_saved_state_lands_under_data_dir(self):
        folder = tempfile.mkdtemp()
        run("set", "--balance", "100", data_dir=folder)
        self.assertTrue((Path(folder) / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
