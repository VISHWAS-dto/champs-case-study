"""Phase 2 - Funnel analysis of the BrightChamps FDA case dataset.

Counts how many leads reach each stage of
    Lead -> Demo Scheduled -> Demo Joined -> Demo Completed -> Converted
and how many drop off between stages. Every number is computed from the CSV.
No interventions and no revenue-loss claims.

Usage:
    python3 analysis/phase_02_funnel_analysis.py [path/to/csv]

Writes:
    results/phase_02_funnel_analysis.md
    results/figures/phase_02/01_funnel_dropoff.png
"""

import sys
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_PATHS = [
    ROOT / "data" / "BrightChamps_FDA_Case_Dataset.csv",
    ROOT / "BrightChamps_FDA_Case_Dataset.csv",
]
OUT_PATH = ROOT / "results" / "phase_02_funnel_analysis.md"
FIG_DIR = ROOT / "results" / "figures" / "phase_02"
TS_FORMAT = "%Y-%m-%d %H:%M"

# Same palette as Phase 1 charts.
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
DROP = "#d9d7d1"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 14, "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2,
    "text.color": TEXT, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.6,
})

STAGES = ["Lead", "Demo Scheduled", "Demo Joined", "Demo Completed", "Converted"]
# Name of the group that leaves the funnel between stage i-1 and stage i.
DROP_NAMES = [None, "Demo not scheduled", "Demo no-show", "Demo not completed",
              "Completed, not converted"]


def resolve_csv():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    sys.exit(f"CSV not found. Looked in: {', '.join(str(p) for p in CANDIDATE_PATHS)}")


def pct(n, d, places=1):
    return f"{n / d * 100:.{places}f}%" if d else "n/a"


def md_table(frame):
    """Render a DataFrame as a padded GitHub markdown table; numeric columns right-aligned."""
    cols = [str(c) for c in frame.columns]
    rows = [[str(v) for v in row] for row in frame.itertuples(index=False)]
    numeric = [
        bool(rows) and all(r[i] in ("", "—") or r[i].replace(",", "").replace(".", "", 1)
                           .rstrip("%").lstrip("-").isdigit() for r in rows)
        for i in range(len(cols))
    ]
    widths = [max(3, len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]

    def fmt(cells):
        return "| " + " | ".join(
            cell.rjust(w) if num else cell.ljust(w)
            for cell, w, num in zip(cells, widths, numeric)
        ) + " |"

    sep = "| " + " | ".join(("-" * (w - 1) + ":") if num else "-" * w
                            for w, num in zip(widths, numeric)) + " |"
    return "\n".join([fmt(cols), sep, *(fmt(r) for r in rows)])


def load(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["created_at"] = pd.to_datetime(df["created_at"], format=TS_FORMAT)
    df["demo_scheduled_at"] = pd.to_datetime(df["demo_scheduled_at"].str.strip().replace("", None),
                                             format=TS_FORMAT)
    # Stage flags. "Scheduled" = demo_scheduled_at is filled in (see Phase 1, open question 2).
    df["scheduled"] = df["demo_scheduled_at"].notna()
    df["joined"] = df["demo_joined"].eq("Y")
    df["completed"] = df["demo_completed"].eq("Y")
    df["converted_f"] = df["converted"].eq("Y")
    return df


def stage_counts(df):
    return [len(df), int(df["scheduled"].sum()), int(df["joined"].sum()),
            int(df["completed"].sum()), int(df["converted_f"].sum())]


def verify(df, counts):
    """Hard checks: the funnel must be nested and the exit groups must add up to all leads."""
    assert df["lead_id"].is_unique, "duplicate lead_id"
    assert not (df["joined"] & ~df["scheduled"]).any(), "joined without a scheduled demo"
    assert not (df["completed"] & ~df["joined"]).any(), "completed without joining"
    assert not (df["converted_f"] & ~df["completed"]).any(), "converted without completing"
    assert all(a >= b for a, b in zip(counts, counts[1:])), "stage counts not decreasing"
    drops = [counts[i - 1] - counts[i] for i in range(1, len(counts))]
    assert sum(drops) + counts[-1] == counts[0], "drop-offs + converted != total leads"
    return drops


def funnel_chart(counts, drops):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    total = counts[0]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    y = np.arange(len(STAGES))[::-1]
    ax.barh(y, counts, color=BLUE, height=0.62, edgecolor=SURFACE, linewidth=2)
    # Grey segment = leads that were at the previous stage but did not reach this one.
    for i in range(1, len(STAGES)):
        ax.barh(y[i], drops[i - 1], left=counts[i], color=DROP, height=0.62,
                edgecolor=SURFACE, linewidth=2)
    for i, (yi, c) in enumerate(zip(y, counts)):
        ax.text(c / 2 if c > total * 0.12 else c + 40, yi,
                f"{c:,}\n{pct(c, total)} of leads", va="center",
                ha="center" if c > total * 0.12 else "left",
                fontsize=9, color="white" if c > total * 0.12 else TEXT)
        if i:
            d = drops[i - 1]
            ax.text(counts[i - 1] + 40, yi,
                    f"−{d:,} {DROP_NAMES[i].lower()}  ({pct(d, counts[i - 1])} of previous stage)",
                    va="center", fontsize=8.5, color=TEXT_2)
    ax.set_yticks(y, STAGES)
    ax.set_xlim(0, total * 1.55)
    ax.set_xticks(np.arange(0, total + 1, 1000))
    ax.set_xlabel("Leads")
    ax.grid(axis="y", visible=False)
    ax.set_title("BrightChamps funnel, 1 Jun – 31 Jul 2026 leads")
    ax.text(0, 1.01, "Blue = leads that reached the stage. Grey = leads that were at the previous "
            "stage but did not reach this one.", transform=ax.transAxes, fontsize=9,
            color=TEXT_2, va="bottom")
    fig.tight_layout()
    path = FIG_DIR / "01_funnel_dropoff.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    csv = resolve_csv()
    df = load(csv)
    counts = stage_counts(df)
    drops = verify(df, counts)
    L, S, J, C, V = counts
    not_sched, no_show, not_comp, comp_not_conv = drops

    out = []
    w = out.append
    w("# Phase 2 — Funnel Analysis\n")
    w(f"Source file: `{csv.name}`  ")
    w("Generated by: `analysis/phase_02_funnel_analysis.py` (re-run to reproduce).  ")
    w("Scope: exact counts and rates from the dataset. No interventions, no revenue-loss estimates.\n")

    # --- 1. Stage definitions ------------------------------------------------------
    w("## 1. Stage definitions\n")
    w(md_table(pd.DataFrame([
        ["Lead", "every row in the file", "—"],
        ["Demo Scheduled", "`demo_scheduled_at` is not blank", "Lead"],
        ["Demo Joined", "`demo_joined` = Y", "Demo Scheduled"],
        ["Demo Completed", "`demo_completed` = Y", "Demo Joined"],
        ["Converted", "`converted` = Y", "Demo Completed"],
    ], columns=["stage", "rule used", "previous stage"])))
    w("\nThe stages are strictly nested: no lead reaches a stage without the one before it "
      "(checked by the script; see section 6). Treating a blank `demo_scheduled_at` as "
      "\"not scheduled\" is an assumption carried from Phase 1 (open question 2).\n")

    # --- 2. Metrics with formulas --------------------------------------------------
    w("## 2. Requested metrics, with formulas\n")
    w("Letters used in the formulas:\n")
    w(md_table(pd.DataFrame([
        ["L", "total leads", "count(rows)"],
        ["S", "demo scheduled", "count(`demo_scheduled_at` not blank)"],
        ["J", "demo joined", "count(`demo_joined` = Y)"],
        ["C", "demo completed", "count(`demo_completed` = Y)"],
        ["V", "converted", "count(`converted` = Y)"],
    ], columns=["symbol", "meaning", "how it is counted"])))
    w("")
    metrics = [
        ["1", "Total leads", "L", f"{L:,}", "—", "—"],
        ["2", "Demo scheduled", "S", f"{S:,}", "S / L", pct(S, L, 2)],
        ["3", "Demo not scheduled", "L − S", f"{not_sched:,}", "(L − S) / L", pct(not_sched, L, 2)],
        ["4", "Demo joined (join rate)", "J", f"{J:,}", "J / S", pct(J, S, 2)],
        ["5", "Demo no-show", "S − J", f"{no_show:,}", "(S − J) / S", pct(no_show, S, 2)],
        ["6", "Demo completed (completion rate)", "C", f"{C:,}", "C / J", pct(C, J, 2)],
        ["7", "Demo not completed", "J − C", f"{not_comp:,}", "(J − C) / J", pct(not_comp, J, 2)],
        ["8", "Converted (post-demo rate)", "V", f"{V:,}", "V / C", pct(V, C, 2)],
        ["9", "Overall conversion rate", "V", f"{V:,}", "V / L", pct(V, L, 2)],
    ]
    w(md_table(pd.DataFrame(metrics, columns=["#", "metric", "count formula", "count",
                                              "rate formula", "rate"])))
    w("\nWorked rate calculations:\n")
    worked = [
        ["2", "S / L", f"{S:>5,} / {L:>5,}", pct(S, L, 2)],
        ["3", "(L − S) / L", f"{not_sched:>5,} / {L:>5,}", pct(not_sched, L, 2)],
        ["4", "J / S", f"{J:>5,} / {S:>5,}", pct(J, S, 2)],
        ["5", "(S − J) / S", f"{no_show:>5,} / {S:>5,}", pct(no_show, S, 2)],
        ["6", "C / J", f"{C:>5,} / {J:>5,}", pct(C, J, 2)],
        ["7", "(J − C) / J", f"{not_comp:>5,} / {J:>5,}", pct(not_comp, J, 2)],
        ["8", "V / C", f"{V:>5,} / {C:>5,}", pct(V, C, 2)],
        ["9", "V / L", f"{V:>5,} / {L:>5,}", pct(V, L, 2)],
    ]
    w(md_table(pd.DataFrame(worked, columns=["#", "formula", "numbers", "result"])))
    w("\nNo-show is defined as *scheduled but not joined*. The dataset has no field that separates "
      "a no-show from a cancellation or a reschedule, so all three are inside this number.\n")

    # --- 3. Funnel table -----------------------------------------------------------
    w("## 3. Funnel table\n")
    rows = []
    for i, stage in enumerate(STAGES):
        if i == 0:
            rows.append([stage, f"{counts[0]:,}", "100.0%", "—", "—", "—", "—", "—"])
            continue
        d = drops[i - 1]
        rows.append([stage, f"{counts[i]:,}", pct(counts[i], L), pct(counts[i], counts[i - 1]),
                     f"{d:,}", pct(d, counts[i - 1]), pct(d, L), pct(d, L - V)])
    w(md_table(pd.DataFrame(rows, columns=[
        "stage", "leads", "% of leads", "step conv.", "drop-off",
        "drop % prev.", "drop % all", "% of drops"])))
    w("\nColumn formulas, for a stage with count *N* whose previous stage has count *P*:\n")
    w(md_table(pd.DataFrame([
        ["% of leads", "N / L", "share of all leads that reached this stage"],
        ["step conv.", "N / P", "share of the previous stage that moved on"],
        ["drop-off", "P − N", "leads lost between the previous stage and this one"],
        ["drop % prev.", "(P − N) / P", "drop-off rate of this step (= 1 − step conv.)"],
        ["drop % all", "(P − N) / L", "drop-off as a share of all leads"],
        ["% of drops", "(P − N) / (L − V)", "share of all non-converted leads lost here"],
    ], columns=["column", "formula", "meaning"])))
    w(f"\nCheck: {' + '.join(f'{d:,}' for d in drops)} (drop-offs) + {V:,} (converted) "
      f"= {sum(drops) + V:,} = total leads.\n")

    # --- 4. Where each lead ends up ------------------------------------------------
    w("## 4. Where each lead ends up (furthest stage reached)\n")
    w("Every lead falls into exactly one of these five groups.\n")
    exits = [
        ["Not scheduled", "S = N", not_sched],
        ["Scheduled, did not join (no-show)", "S = Y, J = N", no_show],
        ["Joined, did not complete", "J = Y, C = N", not_comp],
        ["Completed, did not convert", "C = Y, V = N", comp_not_conv],
        ["Converted", "V = Y", V],
    ]
    w(md_table(pd.DataFrame(
        [[a, b, f"{n:,}", pct(n, L)] for a, b, n in exits],
        columns=["outcome", "rule", "leads", "% of leads"])))
    w("")

    # --- 5. Maturity of the data -----------------------------------------------------
    w("## 5. Funnel by lead-creation month (data maturity check)\n")
    w("The data extraction date is not given (Phase 1, open question 3). If July leads had less "
      "time to progress, their later-stage rates would be lower. This table only reports what the "
      "file shows; it does not adjust any number above.\n")
    month_rows = []
    for m, g in df.groupby(df["created_at"].dt.to_period("M")):
        c = stage_counts(g)
        month_rows.append([m.strftime("%b %Y"), f"{c[0]:,}", pct(c[1], c[0]), pct(c[2], c[1]),
                           pct(c[3], c[2]), pct(c[4], c[3]), pct(c[4], c[0], 2)])
    day = df["created_at"].dt.normalize()
    last7 = day >= day.max() - timedelta(days=6)
    for label, g in [("25–31 Jul (last 7 days)", df[last7]), ("1 Jun – 24 Jul", df[~last7])]:
        c = stage_counts(g)
        month_rows.append([label, f"{c[0]:,}", pct(c[1], c[0]), pct(c[2], c[1]),
                           pct(c[3], c[2]), pct(c[4], c[3]), pct(c[4], c[0], 2)])
    w(md_table(pd.DataFrame(month_rows, columns=[
        "cohort", "leads", "S / L", "J / S", "C / J", "V / C", "V / L"])))
    w("\nColumns use the letters from section 2: scheduling rate, join rate, completion rate, "
      "post-demo conversion, overall conversion.")

    after = df["demo_scheduled_at"] > df["created_at"].max()
    a = df[after]
    w(f"\nDemos dated after the last lead was created ({df['created_at'].max():%Y-%m-%d %H:%M}): "
      f"**{len(a)}**. Of these, {int(a['joined'].sum())} joined ({pct(a['joined'].sum(), len(a))}), "
      f"{int(a['completed'].sum())} completed and {int(a['converted_f'].sum())} converted. "
      f"For comparison, the join rate for all scheduled demos is {pct(J, S)}.\n")

    # --- 6. Verification ---------------------------------------------------------------
    w("## 6. Verification performed by the script\n")
    w("All of these are `assert` statements; the script stops if any fails.\n")
    w("- `lead_id` is unique")
    w("- No lead is joined without a scheduled demo, completed without joining, or converted without completing")
    w("- Stage counts never increase down the funnel")
    w("- Sum of all drop-offs + converted = total leads")
    w(f"- Counts match the Phase 1 audit (5,000 / 3,229 / 2,060 / 1,786 / 362)\n")

    # --- 7. Reading notes ----------------------------------------------------------------
    w("## 7. How to read these numbers\n")
    w("- A drop-off is a count of leads that did not reach the next stage. It is **not** a count of "
      "lost sales, and multiplying it by the ₹60,000 revenue per customer does not give lost revenue. "
      "Many of these leads would not have bought under any process; that share is not in the data.")
    w("- The largest drop-off count and the stage where money is recoverable are different questions. "
      "This phase answers only the first.")
    w("- Rates at different stages have different denominators. \"Drop-off % of previous stage\" "
      "compares how leaky each step is; \"drop-off % of all leads\" compares how many leads each "
      "step removes.")
    w("- The no-show group mixes no-shows, cancellations and reschedules; the file cannot tell them apart.\n")

    fig = funnel_chart(counts, drops)
    w("## 8. Funnel chart\n")
    w(f"![Funnel with drop-offs]({fig.relative_to(OUT_PATH.parent).as_posix()})\n")

    if len(sys.argv) == 1:  # only the project CSV has known Phase 1 counts
        assert counts == [5000, 3229, 2060, 1786, 362], f"counts differ from Phase 1 audit: {counts}"

    OUT_PATH.write_text("\n".join(out) + "\n")
    print("Stage counts:", dict(zip(STAGES, counts)))
    print("Drop-offs:", dict(zip(DROP_NAMES[1:], drops)))
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {fig}")


if __name__ == "__main__":
    main()
