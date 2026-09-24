"""Check the rescue-sheet rules with pandas, independently of the JavaScript.

Re-implements Phase 8 §5 (flag, deadline, arm, action) and the A/A readout, and
compares the counts with the acceptance numbers below. The page does not need this
script; it exists so the JavaScript can be checked against pandas.

Default input is the SYNTHETIC sample (sample/demo_export.csv). The confidential case
CSV is not in the repository; if it is placed at the repository root, its acceptance
counts are checked too:  python3 prototype/check_rescue_logic.py BrightChamps_FDA_Case_Dataset.csv

Usage:
    python3 prototype/check_rescue_logic.py [path/to/export.csv] [--as-of "2026-07-15 09:00"] [--rep AD-07]

Exit code 0 if every acceptance check passes (checked on the two known files at the default
"as of"), 1 if any fails, 2 on bad input.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "sample" / "demo_export.csv"
CASE_CSV = HERE.parent / "BrightChamps_FDA_Case_Dataset.csv"  # local only; not committed
DEFAULT_AS_OF = "2026-07-15 09:00"
LATE_H = 48
MIN_MOVE_H = 3  # MOVE only with at least this many hours left before the deadline
REQUIRED = ["lead_id", "created_at", "demo_scheduled_at", "parent_timezone",
            "rep_assigned", "rep_shift", "geography", "demo_joined"]

# Acceptance counts at 2026-07-15 09:00 (the JS tests assert the same numbers).
EXPECTED = {
    "demo_export.csv": {  # synthetic sample
        "late_demos": 461, "late_rescue": 200, "late_control": 261,
        "js_rescue": 0.460, "js_control": 0.441, "flagged": 45, "move": 12, "open_rescue": 6,
    },
    "BrightChamps_FDA_Case_Dataset.csv": {  # case data (Phase 8 §10A, with the 3h MOVE rule)
        "late_demos": 1285, "late_rescue": 629, "late_control": 656,
        "js_rescue": 0.464, "js_control": 0.474, "flagged": 92, "move": 43, "open_rescue": 25,
    },
}


def load(path):
    """Read the export. Raises ValueError with a readable message on bad input."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"File not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(missing)}")
    df = df[df["demo_scheduled_at"].str.strip() != ""].copy()  # never booked
    for col in ("created_at", "demo_scheduled_at"):
        df[col] = pd.to_datetime(df[col], format="%Y-%m-%d %H:%M", errors="coerce")
    bad = df["created_at"].isna() | df["demo_scheduled_at"].isna()
    if bad.any():
        print(f"warning: skipped {bad.sum()} row(s) with unreadable dates", file=sys.stderr)
    no_digit = ~df["lead_id"].str.contains(r"\d")
    if no_digit.any():
        print(f"warning: skipped {no_digit.sum()} row(s) whose lead_id has no digit", file=sys.stderr)
    dup = df["lead_id"].duplicated()
    if dup.any():
        print(f"warning: skipped {dup.sum()} duplicate lead_id row(s) (first kept)", file=sys.stderr)
    return df[~bad & ~no_digit & ~dup]


def arm(lead_ids):
    """Odd last digit -> RESCUE, even -> CONTROL."""
    last = lead_ids.str.extract(r"(\d)\D*$")[0].astype(int)
    return np.where(last % 2 == 1, "RESCUE", "CONTROL")


def late_demos(df, late_h=LATE_H):
    gap_h = (df["demo_scheduled_at"] - df["created_at"]).dt.total_seconds() / 3600
    out = df[gap_h > late_h].copy()
    out["arm"] = arm(out["lead_id"])
    return out


def build_rescue_list(df, as_of, late_h=LATE_H):
    """Phase 8 §5: upcoming late demos as seen at `as_of`, with deadline, arm and action."""
    out = late_demos(df[df["created_at"] <= as_of], late_h)
    out = out[out["demo_scheduled_at"] > as_of].copy()
    out["deadline"] = out["created_at"] + pd.Timedelta(hours=late_h)
    hours_left = (out["deadline"] - as_of).dt.total_seconds() / 3600
    out["action"] = np.where(hours_left >= MIN_MOVE_H, "MOVE", "CONFIRM")  # decide before rounding, as the JS does
    out["hours_left"] = hours_left.round(1)
    out["action_order"] = (out["action"] == "CONFIRM").astype(int)
    return out.sort_values(["action_order", "deadline"]).drop(columns="action_order")


def aa_readout(df, late_h=LATE_H):
    """J/S by arm for every late demo, with a 95% CI on the difference (normal approximation)."""
    late = late_demos(df, late_h)
    result = late["demo_joined"].str.strip().str.upper()
    late = late[result.isin(["Y", "N"])]  # demos not yet held have no result; the JS skips them too
    joined = result[late.index] == "Y"
    res = {}
    for a in ("RESCUE", "CONTROL"):
        m = late["arm"] == a
        n = int(m.sum())
        res[a] = {"n": n, "joined": int(joined[m].sum()), "rate": float(joined[m].mean()) if n else float("nan")}
    if not (res["RESCUE"]["n"] and res["CONTROL"]["n"]):
        res["diff"] = res["lo"] = res["hi"] = float("nan")
        return res
    p1, n1, p2, n2 = res["RESCUE"]["rate"], res["RESCUE"]["n"], res["CONTROL"]["rate"], res["CONTROL"]["n"]
    diff = p1 - p2
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    res["diff"], res["lo"], res["hi"] = diff, diff - 1.96 * se, diff + 1.96 * se
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    ap.add_argument("--as-of", default=DEFAULT_AS_OF, help='export-clock time, e.g. "2026-07-15 09:00"')
    ap.add_argument("--rep", default="AD-02", help="rep whose list to print")
    args = ap.parse_args(argv)

    try:
        as_of = pd.Timestamp(args.as_of)
        if pd.isna(as_of):
            raise ValueError("--as-of is empty")
        df = load(args.csv)
    except (ValueError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    lst = build_rescue_list(df, as_of)
    open_ = lst[lst["action"] == "MOVE"]
    open_rescue = open_[open_["arm"] == "RESCUE"]
    aa = aa_readout(df)

    print(f"Run as of {as_of:%Y-%m-%d %H:%M} on {Path(args.csv).name}")
    open_rescue_n = len(open_rescue)
    for label, value in [(f"upcoming demos, slot >{LATE_H}h after lead", len(lst)),
                         (f"...>={MIN_MOVE_H}h to deadline (MOVE)", len(open_)),
                         (f"...<{MIN_MOVE_H}h or passed (CONFIRM)", len(lst) - len(open_)),
                         ("open rows rescue / control", f"{open_rescue_n} / {len(open_) - open_rescue_n}")]:
        print(f"  {label:<40}: {value}")
    by_shift = open_rescue["rep_shift"].value_counts().to_dict()
    print(f"  {'open rescue rows by shift':<40}: {by_shift}")

    rep_rows = lst[(lst["arm"] == "RESCUE") & (lst["rep_assigned"] == args.rep)].head(5)
    print(f"\nRep view {args.rep} (top 5, deadline in export clock):")
    for r in rep_rows.itertuples():
        print(f"  {r.lead_id}  {r.geography:<12} deadline {r.deadline:%Y-%m-%d %H:%M}  "
              f"{r.hours_left:>6.1f} h  {r.action}")

    print("\nA/A readout (every late demo in the export; outcome log not used):")
    for a in ("RESCUE", "CONTROL"):
        print(f"  {a:<8} n={aa[a]['n']:<5} J/S={aa[a]['rate']:.1%}")
    print(f"  difference {aa['diff'] * 100:+.1f} pp, 95% CI {aa['lo'] * 100:+.1f} to {aa['hi'] * 100:+.1f} pp")

    expected = EXPECTED.get(Path(args.csv).name)
    if expected is None or args.as_of != DEFAULT_AS_OF:
        return 0

    got = {
        "late_demos": aa["RESCUE"]["n"] + aa["CONTROL"]["n"],
        "late_rescue": aa["RESCUE"]["n"],
        "late_control": aa["CONTROL"]["n"],
        "js_rescue": round(aa["RESCUE"]["rate"], 3),
        "js_control": round(aa["CONTROL"]["rate"], 3),
        "flagged": len(lst),
        "move": len(open_),
        "open_rescue": len(open_rescue),
    }
    print("\nAcceptance checks:")
    ok = True
    for k, want in expected.items():
        passed = got[k] == want
        ok &= passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {k:<13} expected {want}, got {got[k]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
