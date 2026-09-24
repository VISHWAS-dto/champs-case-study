"""Generate the SYNTHETIC sample data for the rescue sheet's "Load sample data" button.

Nothing here comes from the confidential case CSV. Leads, reps, timestamps and outcomes are drawn from
a seeded random generator with the same 12-column schema, so the page and tests can be demonstrated
publicly. The join-rate effect in the rescue arm is SIMULATED and is not evidence of anything.

Usage:
    python3 prototype/sample/make_demo_data.py

Writes (next to this file):
    demo_export.csv           synthetic CRM export (12 columns)
    rescue_outcomes_demo.csv  SIMULATED outcome log for rescue rows listed before the sample "as of"
    demo_data.js              the three sample inputs (export, outcome log, first-seen register) as one
                              script, so the page can load them offline with no file picker
"""

import csv
import io
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20260924
N_LEADS = 2000
START = datetime(2026, 6, 1)
DAYS = 61
AS_OF = datetime(2026, 7, 15, 9, 0)  # the sample "Run as of"
RUN_HOUR = 9                         # the daily list is built at 09:00 export clock
LATE_H = 48
MIN_MOVE_H = 3

GEOS = {  # geography: (timezone, shift, weight)
    "USA": ("America/New_York", "US_SHIFT", 33), "UK": ("Europe/London", "US_SHIFT", 11),
    "India": ("Asia/Kolkata", "IST_SHIFT", 10), "UAE": ("Asia/Dubai", "IST_SHIFT", 9),
    "Saudi Arabia": ("Asia/Riyadh", "IST_SHIFT", 8), "Vietnam": ("Asia/Ho_Chi_Minh", "IST_SHIFT", 16),
    "Singapore": ("Asia/Singapore", "SEA_SHIFT", 6), "Australia": ("Australia/Sydney", "SEA_SHIFT", 7),
}
REPS = {"US_SHIFT": ["AD-01", "AD-02", "AD-03", "AD-04", "AD-05"],
        "IST_SHIFT": ["AD-06", "AD-07", "AD-08", "AD-09", "AD-10"],
        "SEA_SHIFT": ["AD-11", "AD-12"]}
SOURCES = {"Meta": 42, "Google": 24, "Organic": 10, "DSA": 10, "Affiliate": 9, "Referral": 5}
FMT = "%Y-%m-%d %H:%M"


def next_run(t):
    run = t.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    return run if run >= t else run + timedelta(days=1)


def main():
    rng = random.Random(SEED)
    ids = rng.sample(range(10000, 99999), N_LEADS)
    leads, outcomes, register = [], [], {}

    for n in ids:
        lead_id = f"D{n}"  # "D" = demo data; the last digit still sets the arm
        geo = rng.choices(list(GEOS), [g[2] for g in GEOS.values()])[0]
        tz, shift, _ = GEOS[geo]
        created = START + timedelta(minutes=rng.randrange(DAYS * 24 * 60))
        row = dict(lead_id=lead_id, lead_source=rng.choices(list(SOURCES), list(SOURCES.values()))[0],
                   geography=geo, parent_timezone=tz, created_at=created.strftime(FMT), demo_scheduled_at="",
                   rep_assigned=rng.choice(REPS[shift]), rep_shift=shift,
                   follow_up_attempts=rng.choice([0, 1, 1, 2, 2, 3, 4]),
                   demo_joined="N", demo_completed="N", converted="N")
        leads.append(row)
        if rng.random() > 0.65:
            continue  # never booked

        late = rng.random() < 0.40
        gap_h = rng.uniform(LATE_H + 1, 240) if late else rng.uniform(1, LATE_H)
        slot = created + timedelta(hours=gap_h)
        row["demo_scheduled_at"] = slot.strftime(FMT)
        join_p = 0.75

        if late:
            join_p = 0.47
            booked = created + timedelta(hours=min(rng.expovariate(1 / 10), gap_h - 1))
            first_run = next_run(booked)
            deadline = created + timedelta(hours=LATE_H)
            if first_run < slot and first_run <= AS_OF:
                action = "MOVE" if (deadline - first_run).total_seconds() / 3600 >= MIN_MOVE_H else "CONFIRM"
                arm = "RESCUE" if n % 2 else "CONTROL"
                register[lead_id] = dict(first_seen_at=first_run.strftime(FMT), first_action=action, arm=arm,
                                         source="SIMULATED")
                if arm == "RESCUE" and rng.random() < 0.85:  # 85% of listed rescue rows get worked
                    logged = first_run + timedelta(minutes=rng.randrange(10, 170))
                    if action == "MOVE":
                        code = rng.choices(["moved_before_deadline", "confirmed_as_is", "no_answer", "cancelled"],
                                           [45, 25, 25, 5])[0]
                    else:
                        code = rng.choices(["confirmed_as_is", "no_answer", "cancelled"], [60, 35, 5])[0]
                    outcomes.append(dict(lead_id=lead_id, outcome=code, logged_at=logged.strftime(FMT),
                                         source="SIMULATED"))
                    if code == "moved_before_deadline":
                        # The CRM now holds the new, earlier slot (this is why measurement uses the register).
                        new_slot = first_run + timedelta(hours=rng.uniform(1, (deadline - first_run).total_seconds() / 3600))
                        row["demo_scheduled_at"] = new_slot.strftime(FMT)
                        join_p = 0.70  # SIMULATED effect, for the demo only
                    elif code == "confirmed_as_is":
                        join_p = 0.52
                    elif code == "cancelled":
                        join_p = 0.0

        if rng.random() < join_p:
            row["demo_joined"] = "Y"
            if rng.random() < 0.87:
                row["demo_completed"] = "Y"
                if rng.random() < 0.20:
                    row["converted"] = "Y"

    leads.sort(key=lambda r: r["created_at"])
    cols = list(leads[0])
    export_csv = to_csv(leads, cols)
    outcome_csv = to_csv(sorted(outcomes, key=lambda r: r["logged_at"]), ["lead_id", "outcome", "logged_at", "source"])
    (HERE / "demo_export.csv").write_text(export_csv)
    (HERE / "rescue_outcomes_demo.csv").write_text(outcome_csv)
    bundle = dict(asOf=AS_OF.strftime(FMT), pilotFrom="2026-06-01", pilotTo="2026-07-12",
                  exportCsv=export_csv, outcomeCsv=outcome_csv, firstSeen=register)
    (HERE / "demo_data.js").write_text(
        "// SYNTHETIC sample data generated by make_demo_data.py. Not the case data; not evidence.\n"
        "window.RESCUE_SAMPLE = " + json.dumps(bundle, separators=(",", ":")) + ";\n")
    print(f"{len(leads)} synthetic leads, {len(register)} listed late demos, {len(outcomes)} simulated outcomes")


def to_csv(rows, cols):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


if __name__ == "__main__":
    main()
