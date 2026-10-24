"""Checks for scripts/parking_cost.py. Run: python3 -m unittest discover -s tests"""

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "parking_cost.py"

spec = importlib.util.spec_from_file_location("parking_cost", SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

NO_FLAGS = argparse.Namespace(lot=None, tiers=None, max=None, hourly=None, limit_min=None)


def garage():
    return pc.build_spec(NO_FLAGS, pc.load_rates())


def run(*args, home=None):
    env = dict(os.environ, HOME=home or tempfile.mkdtemp())
    env.pop("SKILL_DATA_DIR", None)
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


class GaragePrices(unittest.TestCase):
    def test_tier_boundaries_match_asu_page(self):
        spec = garage()
        expected = {1: 4, 30: 4, 60: 4, 61: 8, 120: 8, 121: 12, 180: 12, 181: 16, 240: 16, 600: 16}
        for minutes, amount in expected.items():
            self.assertEqual(pc.price(minutes, spec), amount, f"{minutes} min")

    def test_price_steps_stop_at_the_cap(self):
        self.assertEqual([(m, o, n) for m, o, n in pc.price_steps(garage())],
                         [(60, 4, 8), (120, 8, 12), (180, 12, 16)])

    def test_override_tiers(self):
        args = argparse.Namespace(lot=None, tiers="60:5,120:9", max=9.0, hourly=None, limit_min=None)
        spec = pc.build_spec(args, pc.load_rates())
        self.assertEqual(pc.price(90, spec), 9)


class LotPrices(unittest.TestCase):
    def lot(self, name):
        args = argparse.Namespace(lot=name, tiers=None, max=None, hourly=None, limit_min=None)
        return pc.build_spec(args, pc.load_rates())

    def test_caps_and_limits(self):
        self.assertEqual(pc.price(300, self.lot("Lot 59")), 15)
        self.assertEqual(pc.price(150, self.lot("lot 9")), 6)
        self.assertEqual(self.lot("Lot 27")["limit_min"], 60)

    def test_unknown_lot_needs_rates(self):
        result = run("cost", "--minutes", "60", "--lot", "Lot 99")
        self.assertEqual(result.returncode, 2)


class Commands(unittest.TestCase):
    def test_bad_input_exit_code(self):
        self.assertEqual(run("cost", "--minutes", "0").returncode, 2)
        self.assertEqual(run("reminders", "--start", "nope").returncode, 2)

    def test_reminders_respect_stay_and_lead(self):
        out = run("reminders", "--start", "2026-10-24T14:30", "--stay", "150").stdout.splitlines()
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].startswith("2026-10-24T15:20 |"))
        self.assertIn("3:30 PM", out[0])

    def test_no_reminders_for_short_stay(self):
        out = run("reminders", "--start", "2026-10-24T14:30", "--stay", "45").stdout
        self.assertIn("No price changes", out)

    def test_session_saves_and_clears_under_home(self):
        home = tempfile.mkdtemp()
        self.assertEqual(run("status", "--now", "2026-10-24T15:00", home=home).returncode, 3)
        saved = run("save", "--name", "Apache Boulevard garage", "--start", "2026-10-24T14:30",
                    "--note", "Level 3", home=home)
        self.assertEqual(saved.returncode, 0)
        self.assertTrue((Path(home) / ".config" / "park-and-go" / "session.json").exists())
        status = run("status", "--now", "2026-10-24T16:05", home=home).stdout
        self.assertIn("Level 3", status)
        self.assertIn("Cost so far: $8", status)
        run("clear", home=home)
        self.assertEqual(run("status", "--now", "2026-10-24T16:05", home=home).returncode, 3)

    def test_sample_leaves_saved_state_alone(self):
        home = tempfile.mkdtemp()
        self.assertEqual(run("--sample", home=home).returncode, 0)
        self.assertFalse((Path(home) / ".config").exists())


if __name__ == "__main__":
    unittest.main()
