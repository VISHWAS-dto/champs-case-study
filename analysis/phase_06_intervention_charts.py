"""Phase 6 — charts for the intervention options (results/phase_06_intervention_options.md).

Four figures in results/figures/phase_06/:
  01_where_options_act.png   join rate by hours-to-demo band, with where each option acts
  02_launch_timeline.png     working days to launch per option vs the two-week limit
  03_option_scorecard.png    the side-by-side comparison as a rated grid
  04_holdout_power.png       detectable join-rate lift vs weeks of 50/50 holdout

Launch days and ratings are the judgments written in the Phase 6 file, not data.
Figures 01 and 04 are computed from the CSV. Usage: python analysis/phase_06_intervention_charts.py [csv]
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from scipy.stats import norm  # noqa: E402

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase_02_funnel_analysis import load, resolve_csv  # noqa: E402
from phase_03_leak_analysis import BLUE, GRID, LATE_H, ORANGE, SURFACE, TEXT, TEXT_2, prepare  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "results" / "figures" / "phase_06"

BANDS = [0, 24, 48, 72, 96, 120, 168, np.inf]
BAND_LABELS = ["0–24h", "24–48h", "48–72h", "72–96h", "96–120h", "120–168h", ">168h"]

# (short name, type, min days, max days) — from the Phase 6 file, section 5 of each option.
OPTIONS = [
    ("1. 48h default booking rule", "process", 3, 5),
    ("2. Reminder sequence for >48h demos", "messaging", 7, 10),
    ("3. Daily Late-Demo Rescue sheet", "spreadsheet", 3, 5),
    ("4. No-show risk score", "scoring", 4, 6),
    ("5. AI WhatsApp rebooking agent", "AI agent", 10, 15),
]
TWO_WEEKS = 10  # working days

# Scorecard: 0 = good, 1 = mixed, 2 = poor (lower is better in every column).
CRITERIA = ["Time to\nlaunch", "Engineering\nneeded", "Ops load", "Adoption\nrisk",
            "Works if cause\nis process (H1)", "Works if cause\nis intent (H2)", "Fits 2 weeks,\nno sprint"]
SCORES = [
    # time, eng, ops, adoption, H1, H2, fits
    ([0, 0, 1, 2, 0, 2, 0], ["3–5d", "none", "medium", "high", "yes", "weak", "yes"]),
    ([1, 0, 0, 1, 1, 1, 0], ["7–10d", "none–low", "low", "low/med", "if reminders", "partial", "yes"]),
    ([0, 0, 1, 1, 0, 1, 0], ["3–5d", "none", "medium", "medium", "yes", "partial", "yes"]),
    ([0, 0, 0, 1, 1, 1, 1], ["4–6d", "none", "low", "medium", "via action", "via action", "adds little"]),
    ([2, 2, 1, 2, 0, 1, 2], ["2–3 wk", "medium", "medium", "high", "yes", "partial", "doubtful"]),
]
# Sequential single hue (blue ramp), light -> dark = better -> worse would read as "more";
# here darker = more concern, so the scale is labelled on the figure.
SCORE_CMAP = ListedColormap(["#e3eefb", "#9cc1ee", "#2a78d6"])


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / name
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)}")


def fig_where_options_act(df):
    s = df[df["scheduled"]].copy()
    s["band"] = pd.cut(s["gap_h"], BANDS, labels=BAND_LABELS)
    g = s.groupby("band", observed=True)["joined"].agg(["size", "mean"])
    x = np.arange(len(g))
    late = [lbl not in ("0–24h", "24–48h") for lbl in g.index]

    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.bar(x, g["mean"] * 100, 0.62, color=[ORANGE if l else BLUE for l in late],
           edgecolor=SURFACE, linewidth=2)
    early_js = s.loc[~s["late"], "joined"].mean() * 100
    late_js = s.loc[s["late"], "joined"].mean() * 100
    for xi, (n, m), l in zip(x, g.itertuples(index=False), late):
        avg = late_js if l else early_js
        ax.text(xi, max(m * 100, avg) + 1.5, f"{m:.0%}", ha="center", fontsize=10, color=TEXT, fontweight="bold")
        ax.text(xi, 3, f"n={n:,}", ha="center", fontsize=8.5, color=SURFACE)
    ax.axvline(1.5, color=TEXT_2, linewidth=1, linestyle="--")
    ax.text(1.55, 97, "48h", fontsize=9, color=TEXT_2, va="top")
    ax.hlines(early_js, -0.4, 1.4, color=BLUE, linewidth=2)
    ax.hlines(late_js, 1.6, len(g) - 0.6, color=ORANGE, linewidth=2)

    # Where each option acts
    ax.annotate("", xy=(0.9, 108), xytext=(4.0, 108),
                arrowprops=dict(arrowstyle="-|>", color=TEXT, linewidth=1.4))
    ax.text(2.45, 110, "Options 1, 3, 5: move the demo inside 48h", ha="center", fontsize=9, color=TEXT)
    ax.text(4.0, 90, "Option 2: reminders for demos\nthat stay >48h out", ha="center", fontsize=9, color=TEXT)
    ax.text(4.0, 80, "Option 4: ranks who to contact;\nlittle to rank past 48h (flat)",
            ha="center", fontsize=9, color=TEXT_2)

    ax.set_xticks(x, g.index)
    ax.set_ylim(0, 118)
    ax.set_yticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    ax.set_xlabel("Hours from lead creation to demo slot")
    ax.set_ylabel("Demos joined (J/S)")
    ax.set_title("Where each option acts on the leak")
    ax.grid(axis="x", visible=False)
    fig.text(0.01, 0.01, f"Blue = within 48h (avg {early_js:.1f}%), orange = more than 48h (avg {late_js:.1f}%). "
             "Join rate drops at 48h and stays flat after it.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, "01_where_options_act.png")


def fig_launch_timeline():
    fig, ax = plt.subplots(figsize=(10, 4.2))
    names = [o[0] for o in OPTIONS][::-1]
    for i, (name, kind, lo, hi) in enumerate(OPTIONS[::-1]):
        fits = hi <= TWO_WEEKS
        ax.barh(i, hi - lo, left=lo, height=0.5, color=BLUE if fits else ORANGE,
                edgecolor=SURFACE, linewidth=2)
        ax.text(hi + 0.25, i, f"{lo}–{hi} working days · {kind}", va="center", fontsize=9, color=TEXT,
                bbox=dict(boxstyle="square,pad=0.15", facecolor=SURFACE, edgecolor="none"))
    ax.axvline(TWO_WEEKS, color=TEXT, linewidth=1.2, linestyle="--")
    ax.text(TWO_WEEKS + 0.15, len(OPTIONS) - 0.45, "two-week limit", fontsize=9, color=TEXT)
    ax.set_yticks(range(len(names)), names)
    ax.set_xlim(0, 22)
    ax.set_xlabel("Working days from start to live")
    ax.set_title("Time to launch vs the two-week limit")
    ax.grid(axis="y", visible=False)
    fig.text(0.01, 0.01, "Blue = fits inside two weeks; orange = over it. Estimates from the Phase 6 file.",
             fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "02_launch_timeline.png")


def fig_scorecard():
    z = np.array([row for row, _ in SCORES])
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.imshow(z, cmap=SCORE_CMAP, vmin=0, vmax=2, aspect="auto")
    for i, (_, labels) in enumerate(SCORES):
        for j, lbl in enumerate(labels):
            ax.text(j, i, lbl, ha="center", va="center", fontsize=9,
                    color=SURFACE if z[i, j] == 2 else TEXT)
    for k in range(1, z.shape[1]):
        ax.axvline(k - 0.5, color=SURFACE, linewidth=2)
    for k in range(1, z.shape[0]):
        ax.axhline(k - 0.5, color=SURFACE, linewidth=2)
    ax.set_xticks(range(len(CRITERIA)), CRITERIA, fontsize=9)
    ax.set_yticks(range(len(OPTIONS)), [o[0] for o in OPTIONS])
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title("Option scorecard (no option selected yet)", pad=40)
    fig.text(0.01, 0.01, "Shading: light = favourable, mid = mixed, dark = concern. "
             "Ratings are judgments from the Phase 6 file.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "03_option_scorecard.png")


def fig_holdout_power(df):
    s = df[df["scheduled"]]
    p = s.loc[s["late"], "joined"].mean()
    per_day = s["late"].sum() / s["created_at"].dt.normalize().nunique()
    weeks = np.linspace(1, 8, 200)
    n_arm = per_day * 7 * weeks / 2
    z = norm.ppf(0.975) + norm.ppf(0.80)
    mde = z * np.sqrt(2 * p * (1 - p) / n_arm) * 100

    early = s.loc[~s["late"], "joined"].mean()
    ceiling = (early - p) * 100
    planning = 24.65 * 0.5  # Phase 5: lower 95% CI of the gap x 50% causal share

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(weeks, mde, color=BLUE, linewidth=2)
    for y, lbl, c in [(ceiling, f"Ceiling: whole gap closed ({ceiling:.1f} pp)", TEXT_2),
                      (planning, f"Phase 5 planning case ({planning:.1f} pp)", ORANGE)]:
        ax.axhline(y, color=c, linewidth=1.4, linestyle="--")
        ax.text(7.95, y + 0.6, lbl, ha="right", fontsize=9, color=TEXT)
    cross = weeks[np.argmax(mde <= planning)]
    ax.plot([cross], [planning], "o", markersize=8, color=ORANGE, markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(f"~{cross:.1f} weeks", (cross, planning), xytext=(cross + 0.4, planning + 6),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=TEXT_2))
    for wk in (2, 4):
        m = z * np.sqrt(2 * p * (1 - p) / (per_day * 7 * wk / 2)) * 100
        ax.plot([wk], [m], "o", markersize=8, color=BLUE, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(wk + 0.12, m + (0.8 if wk == 2 else -2.2), f"{wk} wk: {m:.1f} pp", fontsize=9, color=TEXT)
    ax.set_xlim(1, 8)
    ax.set_ylim(0, 35)
    ax.set_xlabel("Weeks of 50/50 holdout on demos booked >48h out")
    ax.set_ylabel("Smallest detectable lift in join rate (pp)")
    ax.set_title("How long a holdout must run to see the effect")
    fig.text(0.01, 0.01, f"{per_day:.0f} late demos/day, baseline join rate {p:.1%}, 80% power, two-sided α 0.05. "
             "Applies to options 2, 3 and 5.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "04_holdout_power.png")


def main():
    df = prepare(load(resolve_csv()))
    fig_where_options_act(df)
    fig_launch_timeline()
    fig_scorecard()
    fig_holdout_power(df)


if __name__ == "__main__":
    main()
