"""Tests for check_rescue_logic.py. Run with:  python3 -m unittest discover -s prototype/tests -v"""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_rescue_logic as C  # noqa: E402

HEADER = ("lead_id,lead_source,geography,parent_timezone,created_at,demo_scheduled_at,"
          "rep_assigned,rep_shift,follow_up_attempts,demo_joined,demo_completed,converted")
AS_OF = pd.Timestamp("2026-07-15 09:00")


def write_csv(tmp, *lines):
    p = Path(tmp) / "export.csv"
    p.write_text("\n".join([HEADER, *lines]) + "\n")
    return p


class RescueListTest(unittest.TestCase):
    def test_flag_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            df = C.load(write_csv(
                tmp,
                "L1,x,USA,UTC,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,N,N,N",  # MOVE, rescue
                "L2,x,USA,UTC,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,N,N,N",  # MOVE, control
                "L3,x,USA,UTC,2026-07-12 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,N,N,N",  # CONFIRM
                "L5,x,USA,UTC,2026-07-14 09:00,2026-07-16 09:00,AD-01,US_SHIFT,0,N,N,N",  # exactly 48h
                "L7,x,USA,UTC,2026-07-15 10:00,2026-07-20 09:00,AD-01,US_SHIFT,0,N,N,N",  # created after as-of
                "L9,x,USA,UTC,2026-07-14 09:00,,AD-01,US_SHIFT,0,N,N,N",                  # never booked
            ))
        out = C.build_rescue_list(df, AS_OF)
        self.assertEqual(list(zip(out.lead_id, out.arm, out.action)),
                         [("L1", "RESCUE", "MOVE"), ("L2", "CONTROL", "MOVE"), ("L3", "RESCUE", "CONFIRM")])
        self.assertEqual(out.iloc[0].hours_left, 24.0)

    def test_missing_column_is_a_readable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.csv"
            p.write_text("lead_id,created_at\nL1,2026-07-14 09:00\n")
            with self.assertRaisesRegex(ValueError, "Missing column"):
                C.load(p)

    def test_bad_dates_are_skipped_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write_csv(tmp, "L1,x,USA,UTC,oops,2026-07-17 09:00,AD-01,US_SHIFT,0,N,N,N")
            err = io.StringIO()
            with redirect_stderr(err):
                df = C.load(p)
        self.assertEqual(len(df), 0)
        self.assertIn("skipped 1 row", err.getvalue())


class CaseDataTest(unittest.TestCase):
    def test_acceptance_checks_pass(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = C.main([])
        self.assertEqual(code, 0, out.getvalue())
        self.assertNotIn("FAIL", out.getvalue())

    def test_missing_file_returns_error_code(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(C.main(["does/not/exist.csv"]), 2)


if __name__ == "__main__":
    unittest.main()
