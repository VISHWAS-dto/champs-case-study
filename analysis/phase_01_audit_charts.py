"""Phase 1 - Visual version of the data audit.

Draws the Phase 1 audit results as charts so they can be read at a glance.
Describes the data only; no business conclusions.

Usage:
    python3 analysis/phase_01_audit_charts.py [path/to/csv]

Writes:
    results/figures/phase_01/*.png
    results/phase_01_data_audit_visual.md
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_PATHS = [
    ROOT / "data" / "BrightChamps_FDA_Case_Dataset.csv",
    ROOT / "BrightChamps_FDA_Case_Dataset.csv",
]
FIG_DIR = ROOT / "results" / "figures" / "phase_01"
REPORT = ROOT / "results" / "phase_01_data_audit_visual.md"
TS_FORMAT = "%Y-%m-%d %H:%M"

# Palette (validated with the dataviz skill's validate_palette.js):
# categorical slots 1-3 pass all-pairs CVD checks; the blue ordinal ramp passes --ordinal.
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
SHIFT_COLORS = {"US_SHIFT": "#2a78d6", "IST_SHIFT": "#eb6834", "SEA_SHIFT": "#1baf7a"}
ORDINAL = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]
SEQ_CMAP = LinearSegmentedColormap.from_list(
    "blue_seq", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 14, "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2,
    "text.color": TEXT, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.6,
})


def resolve_csv():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    sys.exit(f"CSV not found. Looked in: {', '.join(str(p) for p in CANDIDATE_PATHS)}")


def subtitle(ax, text):
    ax.text(0, 1.01, text, transform=ax.transAxes, fontsize=9, color=TEXT_2, va="bottom")


def save(fig, name):
    fig.tight_layout()
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def hbar(ax, labels, values, total, color=BLUE):
    """Horizontal bars, largest on top, each labelled with count and share."""
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, color=color, height=0.62, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, labels)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(values) * 1.22)
    for yi, v in zip(y, values):
        ax.text(v + max(values) * 0.01, yi, f"{v:,}  ({v / total:.1%})", va="center", fontsize=9, color=TEXT_2)


def main():
    csv_path = resolve_csv()
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    n = len(raw)
    created = pd.to_datetime(raw["created_at"], format=TS_FORMAT)
    demo = pd.to_datetime(raw["demo_scheduled_at"].replace("", pd.NA), format=TS_FORMAT)
    fu = raw["follow_up_attempts"].astype(int)
    scheduled = demo.notna()
    joined, completed, converted = (raw[c] == "Y" for c in ["demo_joined", "demo_completed", "converted"])
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    figs = {}

    # 1. Data health scorecard ---------------------------------------------------
    hard_errors = int(
        raw.duplicated().sum() + raw["lead_id"].duplicated().sum()
        + (~raw[["demo_joined", "demo_completed", "converted"]].isin(["Y", "N"])).sum().sum()
        + (joined & ~scheduled).sum() + (completed & ~joined).sum() + (converted & ~completed).sum()
        + (fu < 0).sum() + ((demo - created).dt.total_seconds() < 0).sum())
    tiles = [
        (f"{n:,}", "rows (leads)"),
        (f"{raw.shape[1]}", "columns, all as\nnamed in the PDF"),
        (f"{hard_errors}", "hard errors\n(dupes, bad values,\nbroken funnel order)"),
        (f"{(~scheduled).mean():.1%}", "blank demo_scheduled_at\n(the only column\nwith blanks)"),
        ("2", "timestamp columns\nwith no timezone"),
    ]
    fig, axes = plt.subplots(1, len(tiles), figsize=(12, 2.6))
    for ax, (big, small) in zip(axes, tiles):
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0.03, 0.03), 0.94, 0.94, transform=ax.transAxes,
                                   facecolor="#f4f3f0", edgecolor="none"))
        ax.text(0.5, 0.66, big, ha="center", va="center", fontsize=26, fontweight="bold", color=TEXT)
        ax.text(0.5, 0.26, small, ha="center", va="center", fontsize=9, color=TEXT_2)
    fig.suptitle("Data health at a glance", x=0.01, ha="left", fontsize=13, fontweight="bold")
    figs["01_data_health"] = (save(fig, "01_data_health"),
                              "The file is structurally clean. The open issues are about meaning "
                              "(blank demo dates, missing timezone), not broken values.")

    # 2. Funnel ------------------------------------------------------------------
    stages = ["All leads", "Demo scheduled", "Demo joined", "Demo completed", "Converted"]
    counts = [n, int(scheduled.sum()), int(joined.sum()), int(completed.sum()), int(converted.sum())]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(stages))[::-1]
    ax.barh(y, counts, color=ORDINAL, height=0.66, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, stages)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, n * 1.3)
    for i, (yi, c) in enumerate(zip(y, counts)):
        step = "" if i == 0 else f"   ·   {c / counts[i - 1]:.0%} of previous stage"
        ax.text(c + n * 0.01, yi, f"{c:,}  ({c / n:.1%} of leads){step}", va="center", fontsize=9, color=TEXT_2)
    ax.set_xlabel("Leads")
    ax.set_title("How many leads reach each funnel stage")
    subtitle(ax, "Counts from the Y/N flags; 'scheduled' = demo_scheduled_at is not blank")
    figs["02_funnel"] = (save(fig, "02_funnel"),
                         "Of 5,000 leads, 3,229 have a demo date, 2,060 joined, 1,786 completed and 362 converted. "
                         "No lead skips a stage.")

    # 3. Lead source -------------------------------------------------------------
    vc = raw["lead_source"].value_counts()
    fig, ax = plt.subplots(figsize=(9, 3.6))
    hbar(ax, vc.index.tolist(), vc.values.tolist(), n)
    ax.set_xlabel("Leads")
    ax.set_title("Leads by source")
    figs["03_lead_source"] = (save(fig, "03_lead_source"),
                              "Meta and Google bring 66% of leads. 'DSA' is not defined in the assignment.")

    # 4. Geography ---------------------------------------------------------------
    vc = raw["geography"].value_counts()
    tz = raw.groupby("geography")["parent_timezone"].first()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    hbar(ax, [f"{g}  ({tz[g]})" for g in vc.index], vc.values.tolist(), n)
    ax.set_xlabel("Leads")
    ax.set_title("Leads by geography (each has exactly one timezone)")
    figs["04_geography"] = (save(fig, "04_geography"),
                            "A third of leads are from the USA. Every geography maps to a single parent_timezone.")

    # 5. Reps by shift -----------------------------------------------------------
    reps = raw.groupby(["rep_assigned", "rep_shift"]).size().reset_index(name="leads")
    order = ["US_SHIFT", "IST_SHIFT", "SEA_SHIFT"]
    reps["o"] = reps["rep_shift"].map(order.index)
    reps = reps.sort_values(["o", "rep_assigned"])
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(reps))
    ax.bar(x, reps["leads"], color=reps["rep_shift"].map(SHIFT_COLORS), width=0.7,
           edgecolor=SURFACE, linewidth=2)
    ax.set_xticks(x, reps["rep_assigned"])
    ax.grid(axis="x", visible=False)
    for xi, v in zip(x, reps["leads"]):
        ax.text(xi, v + 6, f"{v}", ha="center", fontsize=8.5, color=TEXT_2)
    handles = [plt.Rectangle((0, 0), 1, 1, color=SHIFT_COLORS[s]) for s in order]
    shift_tot = raw["rep_shift"].value_counts()
    shift_reps = reps.groupby("rep_shift").size()
    ax.legend(handles, [f"{s}: {shift_reps[s]} reps, {shift_tot[s]:,} leads" for s in order],
              frameon=False, loc="upper right", fontsize=9)
    ax.set_ylim(0, reps["leads"].max() * 1.25)
    ax.set_ylabel("Leads")
    ax.set_title("Leads per rep, coloured by shift")
    subtitle(ax, "Each rep appears on exactly one shift")
    figs["05_reps_by_shift"] = (save(fig, "05_reps_by_shift"),
                                "12 reps: 5 on US_SHIFT, 5 on IST_SHIFT, 2 on SEA_SHIFT. "
                                "Shift working hours are not given.")

    # 6. Leads created per day ---------------------------------------------------
    daily = created.dt.floor("D").value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(daily.index, daily.values, color=BLUE, linewidth=2)
    ax.set_ylim(0, daily.max() * 1.2)
    ax.set_ylabel("Leads created")
    ax.set_title("Leads created per day, 1 June – 31 July 2026")
    subtitle(ax, f"Every one of the 61 days has leads; min {daily.min()}, median {int(daily.median())}, "
                 f"max {daily.max()} per day")
    fig.autofmt_xdate()
    figs["06_leads_per_day"] = (save(fig, "06_leads_per_day"),
                                "Lead volume is steady across both months (2,504 in June, 2,496 in July), "
                                "with no gaps in the date range.")

    # 7. Gap between lead creation and demo --------------------------------------
    gap_h = ((demo - created).dt.total_seconds() / 3600).dropna()
    fig, ax = plt.subplots(figsize=(10, 3.8))
    bins = np.arange(0, gap_h.max() + 12, 12)
    ax.hist(gap_h, bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=1.5)
    med = gap_h.median()
    ax.axvline(med, color=TEXT, linewidth=1)
    ax.text(med + 3, ax.get_ylim()[1] * 0.9, f"median {med:.0f}h", fontsize=9, color=TEXT)
    ax.set_xticks(np.arange(0, gap_h.max() + 24, 24))
    ax.set_xlabel("Hours from created_at to demo_scheduled_at (12-hour bins)")
    ax.set_ylabel("Leads")
    ax.grid(axis="x", visible=False)
    ax.set_title("Time from lead creation to demo date")
    subtitle(ax, f"{len(gap_h):,} leads with a demo date · shortest gap exactly {gap_h.min():.0f}h · "
                 f"{(gap_h > 168).sum()} over 7 days")
    figs["07_created_to_demo_gap"] = (save(fig, "07_created_to_demo_gap"),
                                      "Half of demos are within about 27 hours of lead creation. None are earlier "
                                      "than 1 hour and none are negative.")

    # 8. Follow-up attempts ------------------------------------------------------
    vc = fu.value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar(vc.index, vc.values, color=BLUE, width=0.7, edgecolor=SURFACE, linewidth=2)
    for xi, v in zip(vc.index, vc.values):
        ax.text(xi, v + 15, f"{v / n:.1%}", ha="center", fontsize=8.5, color=TEXT_2)
    ax.set_xticks(vc.index)
    ax.set_xlabel("follow_up_attempts")
    ax.set_ylabel("Leads")
    ax.set_ylim(0, vc.max() * 1.15)
    ax.grid(axis="x", visible=False)
    ax.set_title("Follow-up attempts per lead")
    subtitle(ax, "Whole numbers 0–9, none negative; what counts as an attempt is not defined")
    figs["08_follow_up_attempts"] = (save(fig, "08_follow_up_attempts"),
                                     "Most leads get 1–2 follow-ups; 15.3% get none. Values above 6 are rare "
                                     "(1% of leads) but not invalid.")

    # 9. Hour of day by geography (timezone question) ----------------------------
    geo_order = raw["geography"].value_counts().index
    heat = (pd.crosstab(raw["geography"], created.dt.hour, normalize="index")
            .reindex(index=geo_order, columns=range(24), fill_value=0) * 100)
    fig, ax = plt.subplots(figsize=(11, 4))
    im = ax.imshow(heat.values, aspect="auto", cmap=SEQ_CMAP, vmin=0)
    ax.set_xticks(range(24), [f"{h:02d}" for h in range(24)], fontsize=8)
    ax.set_yticks(range(len(geo_order)), geo_order)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.set_label("% of that geography's leads", color=TEXT_2)
    cb.outline.set_visible(False)
    ax.set_xlabel("Hour of created_at, as stored (timezone unknown)")
    ax.set_title("When leads are created, by geography")
    subtitle(ax, f"Every hour holds roughly 1/24 (~{100 / 24:.1f}%) of leads in every geography: no day/night pattern")
    figs["09_hour_by_geography"] = (save(fig, "09_hour_by_geography"),
                                    "Leads are spread almost evenly across all 24 hours in every geography, with no "
                                    "day/night pattern. So the hour of day cannot tell us which clock the timestamps "
                                    "use; that has to be a written assumption.")

    # Report --------------------------------------------------------------------
    lines = [
        "# Phase 1 — Data Audit, in charts\n",
        "Generated by `analysis/phase_01_audit_charts.py`. Full tables and exact numbers: "
        "[phase_01_data_audit.md](phase_01_data_audit.md). These charts describe the data only; "
        "no business conclusions yet.\n",
    ]
    titles = {
        "01_data_health": "1. Is the data clean?",
        "02_funnel": "2. How far do leads get?",
        "03_lead_source": "3. Where do leads come from?",
        "04_geography": "4. Which countries?",
        "05_reps_by_shift": "5. Reps and shifts",
        "06_leads_per_day": "6. Leads over time",
        "07_created_to_demo_gap": "7. How soon is the demo?",
        "08_follow_up_attempts": "8. Follow-up attempts",
        "09_hour_by_geography": "9. The timezone question",
    }
    for key, (path, takeaway) in figs.items():
        lines.append(f"## {titles[key]}\n")
        lines.append(f"![{titles[key]}]({path.relative_to(REPORT.parent).as_posix()})\n")
        lines.append(f"**What it shows:** {takeaway}\n")
    lines.append("## Still unknown (not answerable from the data or the PDF)\n")
    lines += [
        "- Which clock the timestamps use (UTC, IST, or the parent's local time)",
        "- Whether `demo_scheduled_at` is the demo time or the booking time, and what a blank means",
        "- The date the data was extracted, so recent leads may not have finished their journey",
        "- What counts as a follow-up attempt",
        "- Shift working hours, and what 'DSA' stands for",
    ]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(figs)} charts to {FIG_DIR}")
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()
