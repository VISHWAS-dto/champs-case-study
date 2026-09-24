"""Phase 7 — charts for the selected lever (results/phase_07_selected_lever.md).

Four figures in results/figures/phase_07/:
  01_rescue_deadline.png   why a moved demo must land before created_at + 48h
  02_lift_to_money.png     join-rate lift on late demos vs monthly revenue, with the pilot's detection limit
  03_rep_workload.png      rescue rows per rep per day, by shift
  04_pilot_timeline.png    build, launch and 4-week measured pilot vs the two-week limit

Figures 01–03 are computed from the CSV. Figure 04 plots the plan written in the Phase 7 file.
Usage: python analysis/phase_07_lever_charts.py [csv]
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase_02_funnel_analysis import load, resolve_csv  # noqa: E402
from phase_03_leak_analysis import BLUE, GRID, ORANGE, SURFACE, TEXT, TEXT_2, prepare  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "results" / "figures" / "phase_07"

BANDS = [0, 24, 48, 72, 96, 120, 168, np.inf]
BAND_LABELS = ["0–24h", "24–48h", "48–72h", "72–96h", "96–120h", "120–168h", ">168h"]
REVENUE = 60_000  # per customer (assignment)
MONTHS = 2
PILOT_WEEKS = 4
TWO_WEEKS = 10  # working days


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / name
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)}")


def rates(df):
    s = df[df["scheduled"]]
    late, early = s[s["late"]], s[~s["late"]]
    v_per_join = early["converted_f"].sum() / early["joined"].sum()  # baseline C/J x V/C
    per_day = len(late) / s["created_at"].dt.normalize().nunique()
    return s, late, early, v_per_join, per_day


def fig_rescue_deadline(df):
    s, late, *_ = rates(df)
    s = s.copy()
    s["band"] = pd.cut(s["gap_h"], BANDS, labels=BAND_LABELS)
    g = s.groupby("band", observed=True)["joined"].agg(["size", "mean"])
    x = np.arange(len(g))
    is_late = [lbl not in ("0–24h", "24–48h") for lbl in g.index]
    median_h = late["gap_h"].median()

    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.bar(x, g["mean"] * 100, 0.62, color=[ORANGE if l else BLUE for l in is_late],
           edgecolor=SURFACE, linewidth=2)
    for xi, (n, m) in zip(x, g.itertuples(index=False)):
        ax.text(xi, m * 100 + 1.5, f"{m:.0%}", ha="center", fontsize=10, color=TEXT, fontweight="bold")
        ax.text(xi, 3, f"n={n:,}", ha="center", fontsize=8.5, color=SURFACE)
    ax.axvline(1.5, color=TEXT, linewidth=1.2, linestyle="--")
    ax.text(1.45, 113, "rescue deadline\n= created_at + 48h", ha="right", va="top", fontsize=9, color=TEXT)

    # A typical late demo (median gap sits in the 96–120h band) and the two ways to move it.
    src = 4
    ax.plot([src], [g["mean"].iloc[src] * 100 + 10], "v", markersize=9, color=TEXT)
    ax.text(src + 0.35, g["mean"].iloc[src] * 100 + 10, f"typical late demo\n(median {median_h:.0f}h)",
            va="center", fontsize=9, color=TEXT)
    ax.annotate("", xy=(0.95, 88), xytext=(src - 0.1, 88),
                arrowprops=dict(arrowstyle="-|>", color=BLUE, linewidth=1.8))
    ax.text(2.45, 90, "moved before the deadline → joins like ≤48h demos", ha="center", fontsize=9, color=TEXT)
    ax.annotate("", xy=(2.05, 72), xytext=(src - 0.1, 72),
                arrowprops=dict(arrowstyle="-|>", color=TEXT_2, linewidth=1.4, linestyle="--"))
    ax.text(3.0, 74, "moved but still >48h → no gain", ha="center", fontsize=9, color=TEXT_2)

    ax.set_xticks(x, g.index)
    ax.set_ylim(0, 118)
    ax.set_yticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    ax.set_xlabel("Hours from lead creation to demo slot")
    ax.set_ylabel("Demos joined (J/S)")
    ax.set_title("A rescue only helps if the new slot lands before created_at + 48h")
    ax.grid(axis="x", visible=False)
    fig.text(0.01, 0.01, "Blue = within 48h, orange = more than 48h. Past 48h the join rate is flat, "
             "so the target is the deadline, not just 'earlier'. Arrows = design logic.",
             fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, "01_rescue_deadline.png")


def fig_lift_to_money(df):
    _, late, early, v_per_join, per_day = rates(df)
    n_late = len(late)
    p = late["joined"].mean()
    ceiling_pp = (early["joined"].mean() - p) * 100
    per_pp = n_late * 0.01 * v_per_join * REVENUE / MONTHS  # Rs per month per pp of lift

    z = norm.ppf(0.975) + norm.ppf(0.80)
    n_arm = per_day * 7 * PILOT_WEEKS / 2
    mde = z * np.sqrt(2 * p * (1 - p) / n_arm) * 100

    lift = np.linspace(0, 30, 200)
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.axvspan(0, mde, color=GRID, alpha=0.7, linewidth=0)
    ax.text(mde / 2, 19.3, f"too small to detect\nin a {PILOT_WEEKS}-week pilot\n(< {mde:.1f} pp)",
            ha="center", va="top", fontsize=9, color=TEXT_2)
    ax.plot(lift, lift * per_pp / 1e5, color=BLUE, linewidth=2)

    points = [
        (24.65 * 0.25, "25% causal", TEXT_2),
        (24.65 * 0.50, "planning case", ORANGE),
        (ceiling_pp, "ceiling", BLUE),
    ]
    for pp, lbl, c in points:
        y = pp * per_pp / 1e5
        ax.plot([pp], [y], "o", markersize=9, color=c, markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
        ax.text(pp + 0.5, y - 1.1, f"{lbl}: +{pp:.1f} pp\nJ/S {p * 100 + pp:.1f}% → ₹{y:.2f} lakh/mo",
                fontsize=9, color=TEXT)

    ax.set_xlim(0, 30)
    ax.set_ylim(0, 20)
    ax.set_xlabel(f"Lift in join rate on demos booked >48h out (pp, baseline {p:.1%})")
    ax.set_ylabel("Modeled revenue (₹ lakh / month)")
    ax.set_title("What each point of join-rate lift is worth")
    fig.text(0.01, 0.01, f"₹{per_pp:,.0f}/month per pp = {n_late:,} late demos × 1 pp × {v_per_join:.1%} "
             f"customers per joiner × ₹60,000 ÷ 2 months. Detection: 50/50 holdout, {per_day:.0f} late demos/day, "
             "80% power.", fontsize=8.5, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "02_lift_to_money.png")


def fig_rep_workload(df):
    s, *_ = rates(df)
    days = s["created_at"].dt.normalize().nunique()
    g = s.groupby("rep_shift").agg(late=("late", "sum"), reps=("rep_assigned", "nunique"))
    g["late_day"] = g["late"] / days
    g["per_rep"] = g["late_day"] / g["reps"]
    g["rescue_per_rep"] = g["per_rep"] / 2  # half go to the control arm
    g = g.sort_values("rescue_per_rep")
    labels = [i.replace("_SHIFT", "") for i in g.index]
    y = np.arange(len(g))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.barh(y, g["rescue_per_rep"], 0.5, color=BLUE, edgecolor=SURFACE, linewidth=2)
    for yi, r in zip(y, g.itertuples()):
        mins = r.rescue_per_rep * 5
        ax.text(r.rescue_per_rep + 0.03, yi,
                f"{r.rescue_per_rep:.2f} rows/rep/day ≈ {mins:.0f} min  "
                f"({r.late_day:.1f} late demos/day, {r.reps} reps)", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 2.6)
    ax.set_xlabel("Rescue rows per rep per day (after the 50% holdout)")
    ax.set_title("The rescue workload is about one call per rep per day in every shift")
    ax.grid(axis="y", visible=False)
    fig.text(0.01, 0.01, "Computed from the Jun–Jul export over 61 days. Minutes assume ~5 min per call (assumption).",
             fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "03_rep_workload.png")


def fig_pilot_timeline():
    # (label, start working day, end working day, colour) — from section 4.5 / 6 of the Phase 7 file.
    steps = [
        ("Agree columns, codes, holdout", 0, 1, BLUE),
        ("Confirm CRM export", 0, 2, BLUE),
        ("Build sheet / script", 1, 3, BLUE),
        ("Slot capacity check per shift", 2, 3, BLUE),
        ("Shift walkthroughs", 3, 4, BLUE),
        ("Live: daily rescue + checks", 4, 10, ORANGE),
        (f"Measured pilot ({PILOT_WEEKS} weeks)", 4, 4 + PILOT_WEEKS * 5, ORANGE),
    ]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for i, (_, a, b, c) in enumerate(steps[::-1]):
        ax.barh(i, b - a, left=a, height=0.5, color=c, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(range(len(steps)), [s[0] for s in steps[::-1]])
    ax.axvline(TWO_WEEKS, color=TEXT, linewidth=1.2, linestyle="--")
    ax.text(TWO_WEEKS + 0.2, len(steps) - 0.5, "two-week limit", fontsize=9, color=TEXT)
    ax.axvline(4, color=TEXT_2, linewidth=1, linestyle=":")
    ax.text(4.2, -0.75, "go live (day 5)\nbaseline registered", fontsize=8.5, color=TEXT_2)
    end = 4 + PILOT_WEEKS * 5
    ax.plot([end], [0], "D", markersize=9, color=TEXT, markeredgecolor=SURFACE, markeredgewidth=2)
    ax.text(end - 0.3, 0.45, "scale / stop /\ninconclusive", ha="right", fontsize=8.5, color=TEXT)
    ax.set_xlim(0, end + 1)
    ax.set_ylim(-1.2, len(steps) - 0.3)
    ax.set_xlabel("Working days from kick-off")
    ax.set_title("Live on day 5, with five days of buffer before the two-week limit")
    ax.grid(axis="y", visible=False)
    fig.text(0.01, 0.01, "Blue = set-up, orange = running. Plan from the Phase 7 file, not data.",
             fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "04_pilot_timeline.png")


def main():
    df = prepare(load(resolve_csv()))
    fig_rescue_deadline(df)
    fig_lift_to_money(df)
    fig_rep_workload(df)
    fig_pilot_timeline()


if __name__ == "__main__":
    main()
