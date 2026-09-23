"""Phase 3 - Find the leak: where and for whom do leads drop out of the funnel?

Cuts the funnel by lead source, geography, parent timezone, rep, rep shift,
follow-up attempts and the time from lead creation to the scheduled demo, and
tests every segment against the rest of the population. Interactions are checked
for the patterns that survive. Nothing here picks a final leak or a solution:
the output is three candidate leaks with their evidence and alternative explanations.

Usage:
    python3 analysis/phase_03_leak_analysis.py [path/to/csv]

Writes:
    results/phase_03_leak_analysis.md
    results/figures/phase_03/*.png
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from scipy.stats import chi2_contingency, norm  # noqa: E402

sys.dont_write_bytecode = True  # importing Phase 2 helpers should not leave __pycache__ behind
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase_02_funnel_analysis import load, md_table, resolve_csv, stage_counts  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "results" / "phase_03_leak_analysis.md"
FIG_DIR = ROOT / "results" / "figures" / "phase_03"

# Same surface/text/grid as Phases 1-2. Two-series charts use categorical slots 1-2
# (blue, orange); the deviation heatmap uses the blue<->red diverging pair with a grey midpoint.
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
RED = "#e34948"
MID = "#f0efec"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 14, "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2,
    "text.color": TEXT, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.6,
})

LATE_H = 48  # threshold found in the 6-hour join-rate scan (section 4.1)
ALPHA = 0.05
MIN_PP = 5.0  # smallest difference (percentage points) we call operationally meaningful

# (flag column, denominator flag, label). Denominator None = all leads.
STEPS = [("scheduled", None, "Scheduled rate (S/L)"),
         ("joined", "scheduled", "Join rate (J/S)"),
         ("completed", "joined", "Completion rate (C/J)"),
         ("converted_f", "completed", "Post-demo conversion (V/C)"),
         ("converted_f", None, "Overall conversion (V/L)")]
STEP_SHORT = ["S/L", "J/S", "C/J", "V/C", "V/L"]

GAP_BINS = [0, 6, 12, 24, 48, 72, 120, 168, np.inf]
GAP_LABELS = ["≤6h", "6–12h", "12–24h", "24–48h", "48–72h", "72–120h", "120–168h", ">168h"]

DIMENSIONS = [
    ("lead_source", "1. Lead source"),
    ("geography", "2. Geography"),
    ("parent_timezone", "3. Parent timezone"),
    ("rep_assigned", "4. Rep assigned"),
    ("rep_shift", "5. Rep shift"),
    ("fu_band", "6. Follow-up attempts"),
    ("gap_band", "7. Time from lead creation to scheduled demo"),
]


# --------------------------------------------------------------------------- helpers

def pc(x, places=1):
    return "—" if x is None or np.isnan(x) else f"{x * 100:.{places}f}%"


def pp(x):
    return "—" if x is None or np.isnan(x) else f"{x * 100:+.1f} pp"


def rel(a, b):
    return "—" if not b else f"{(a / b - 1) * 100:+.0f}%"


def fmt_p(p):
    if p is None or np.isnan(p):
        return "—"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def two_prop(k1, n1, k0, n0):
    """Difference p1 - p0, its 95% Wald CI, and a two-sided pooled z-test p-value."""
    p1, p0 = k1 / n1, k0 / n0
    diff = p1 - p0
    se = np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    pool = (k1 + k0) / (n1 + n0)
    se0 = np.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n0))
    p = 2 * norm.sf(abs(diff) / se0) if se0 > 0 else np.nan
    return dict(p1=p1, p0=p0, diff=diff, lo=diff - 1.96 * se, hi=diff + 1.96 * se, p=p)


def holm(pvals):
    """Holm step-down adjustment; returns adjusted p-values in the input order."""
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adj[i] = running
    return adj


def mh_risk_diff(frame, exposed, outcome, strata):
    """Mantel-Haenszel weighted risk difference of `outcome` for exposed vs not, within strata.
    Strata lacking either group are dropped. Returns (difference, strata used, rows used)."""
    num = den = 0.0
    used = rows = 0
    for _, g in frame.groupby(strata, observed=True):
        a, b = g[g[exposed]], g[~g[exposed]]
        if len(a) == 0 or len(b) == 0:
            continue
        w = len(a) * len(b) / len(g)
        num += w * (a[outcome].mean() - b[outcome].mean())
        den += w
        used += 1
        rows += len(g)
    return num / den, used, rows


def base(df, denom):
    return df if denom is None else df[df[denom]]


def rates(g):
    L, S, J, C, V = stage_counts(g)
    return dict(L=L, S=S, J=J, C=C, V=V,
                SL=S / L if L else np.nan, JS=J / S if S else np.nan,
                CJ=C / J if J else np.nan, VC=V / C if C else np.nan, VL=V / L if L else np.nan)


# --------------------------------------------------------------------------- data

def prepare(df):
    df["gap_h"] = (df["demo_scheduled_at"] - df["created_at"]).dt.total_seconds() / 3600
    df["gap_band"] = pd.cut(df["gap_h"], GAP_BINS, labels=GAP_LABELS)
    df["gap_band"] = df["gap_band"].cat.add_categories("not scheduled").fillna("not scheduled")
    df["late"] = df["gap_h"] > LATE_H  # False for unscheduled leads; only used on scheduled rows
    df["fu"] = df["follow_up_attempts"].astype(int)
    df["fu_band"] = pd.Categorical(np.where(df["fu"] >= 6, "6+", df["fu"].astype(str)),
                                   ["0", "1", "2", "3", "4", "5", "6+"])
    df["india_vn"] = df["geography"].isin(["India", "Vietnam"])
    df["dsa"] = df["lead_source"].eq("DSA")
    return df


def segment_table(df, col):
    rows = []
    groups = df.groupby(col, observed=True)
    for seg, g in groups:
        r = rates(g)
        rows.append([str(seg), f"{r['L']:,}", pc(r["SL"]), f"{r['S']:,}", pc(r["JS"]),
                     f"{r['J']:,}", pc(r["CJ"]), f"{r['C']:,}", pc(r["VC"]), f"{r['V']:,}",
                     pc(r["VL"], 2)])
    r = rates(df)
    rows.append(["**All leads**", f"{r['L']:,}", pc(r["SL"]), f"{r['S']:,}", pc(r["JS"]),
                 f"{r['J']:,}", pc(r["CJ"]), f"{r['C']:,}", pc(r["VC"]), f"{r['V']:,}",
                 pc(r["VL"], 2)])
    return pd.DataFrame(rows, columns=["segment", "leads", "S/L", "S", "J/S", "J", "C/J", "C",
                                       "V/C", "V", "V/L"])


def screen(df):
    """Every segment of every dimension vs the rest of the population, on every step.
    Returns one row per (dimension, segment, step) plus chi-square tests per (dimension, step)."""
    seg_rows, chi_rows = [], []
    for col, label in DIMENSIONS:
        if col == "parent_timezone":
            continue  # 1:1 with geography (Phase 1); testing it again would double-count
        for (flag, denom, step_label), short in zip(STEPS, STEP_SHORT):
            b = base(df, denom)
            if col == "gap_band":
                if denom is None:
                    continue  # the gap only exists for scheduled leads
                b = b[b["gap_band"] != "not scheduled"]
            tab = pd.crosstab(b[col], b[flag])
            tab = tab[tab.sum(axis=1) > 0]
            chi_p = chi2_contingency(tab)[1] if tab.shape[1] == 2 and len(tab) > 1 else np.nan
            chi_rows.append(dict(dim=label, step=short, groups=len(tab), n=len(b), p=chi_p))
            for seg, g in b.groupby(col, observed=True):
                rest = b[b[col] != seg]
                if len(g) == 0 or len(rest) == 0:
                    continue
                t = two_prop(int(g[flag].sum()), len(g), int(rest[flag].sum()), len(rest))
                seg_rows.append(dict(dim=label, seg=str(seg), step=short, n=len(g), n0=len(rest),
                                     **t))
    seg = pd.DataFrame(seg_rows)
    seg["p_holm"] = holm(seg["p"])
    chi = pd.DataFrame(chi_rows)
    chi["p_holm"] = holm(chi["p"].fillna(1))
    return seg, chi


def local_hour_check(s):
    """Join rate for demos inside vs outside 08:00-21:59 parent-local time, under two
    assumptions for the clock the timestamps are stored in (Phase 1: unknown)."""
    out = []
    for clock in ["UTC", "Asia/Kolkata"]:
        hours = pd.concat([g["demo_scheduled_at"].dt.tz_localize(clock).dt.tz_convert(tz).dt.hour
                           for tz, g in s.groupby("parent_timezone")])
        inside = hours.reindex(s.index).between(8, 21)
        a, b = s[inside], s[~inside]
        t = two_prop(int(a["joined"].sum()), len(a), int(b["joined"].sum()), len(b))
        out.append([f"stored clock = {clock}", f"{len(a):,}", pc(t["p1"]), f"{len(b):,}",
                    pc(t["p0"]), pp(t["diff"]), fmt_p(t["p"])])
    return pd.DataFrame(out, columns=["assumption", "demos 08–22h local", "join rate",
                                      "demos outside", "join rate ", "difference", "p"])


# --------------------------------------------------------------------------- charts

def chart_heatmap(df):
    """Deviation of each segment's step rate from the all-lead rate, in percentage points."""
    dims = [d for d in DIMENSIONS if d[0] not in ("parent_timezone", "gap_band")]
    labels, vals, annots = [], [], []
    overall = rates(df)
    keys = ["SL", "JS", "CJ", "VC", "VL"]
    for col, dlabel in dims:
        for seg, g in df.groupby(col, observed=True):
            r = rates(g)
            name = {"fu_band": f"follow-ups = {seg}"}.get(col, str(seg))
            labels.append(f"{name}  (n={r['L']:,})")
            vals.append([(r[k] - overall[k]) * 100 for k in keys])
            annots.append([pc(r[k]) for k in keys])
    vals = np.array(vals)
    fig, ax = plt.subplots(figsize=(9.2, 11.5))
    cmap = LinearSegmentedColormap.from_list("div", [RED, MID, BLUE])
    lim = 15
    ax.imshow(np.clip(vals, -lim, lim), cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            ax.text(j, i, annots[i][j], ha="center", va="center", fontsize=8,
                    color="white" if abs(vals[i, j]) > 10 else TEXT)
    ax.set_xticks(range(5), ["Scheduled\nS/L", "Joined\nJ/S", "Completed\nC/J",
                             "Converted\nV/C", "Overall\nV/L"])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(labels)), labels, fontsize=8.5)
    ax.grid(False)
    ax.tick_params(length=0)
    # thin separators between dimensions
    edge = 0
    for col, _ in dims[:-1]:
        edge += df[col].nunique()
        ax.axhline(edge - 0.5, color=SURFACE, linewidth=4)
    ax.set_title("Step rates by segment, coloured by gap to the all-lead rate", pad=62)
    ax.text(0, 1.045, f"Blue = above the all-lead rate, red = below (colour saturates at ±{lim} pp).\n"
            f"All-lead rates: S/L {pc(overall['SL'])}, J/S {pc(overall['JS'])}, "
            f"C/J {pc(overall['CJ'])}, V/C {pc(overall['VC'])}, V/L {pc(overall['VL'])}.",
            transform=ax.transAxes, fontsize=8, color=TEXT_2, va="bottom")
    fig.tight_layout()
    path = FIG_DIR / "01_segment_rate_heatmap.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_gap(s):
    bins = list(range(0, 169, 12)) + [np.inf]
    lab = [f"{a}–{b}" for a, b in zip(bins[:-2], bins[1:-1])] + [">168"]
    g = s.groupby(pd.cut(s["gap_h"], bins, labels=lab), observed=True)["joined"].agg(["size", "mean"])
    fig, ax = plt.subplots(figsize=(10, 4.4))
    x = np.arange(len(g))
    colors = [BLUE if b < LATE_H else ORANGE for b in bins[:-1]]
    ax.bar(x, g["mean"] * 100, color=colors, width=0.78, edgecolor=SURFACE, linewidth=2)
    for xi, (n, m) in zip(x, g.itertuples(index=False)):
        ax.text(xi, m * 100 + 1.2, f"{m * 100:.0f}%", ha="center", fontsize=8.5)
        ax.text(xi, 2, f"n={n}", ha="center", fontsize=7.5, color="white")
    ax.axvline(3.5, color=TEXT_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(3.55, 92, f"{LATE_H}h after lead created", fontsize=8.5, color=TEXT_2)
    ax.set_xticks(x, g.index, fontsize=8.5)
    ax.set_xlabel("Hours from lead creation to scheduled demo")
    ax.set_ylabel("Join rate (J/S)")
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="x", visible=False)
    ax.set_title("Join rate drops sharply when the demo is booked more than 48h out")
    ax.text(0, 1.01, "Scheduled leads only (n=3,229). Blue = demo within 48h of lead creation, "
            "orange = later.", transform=ax.transAxes, fontsize=9, color=TEXT_2, va="bottom")
    fig.tight_layout()
    path = FIG_DIR / "02_join_rate_by_gap.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_gap_strata(s):
    panels = [("fu_band", "Follow-up attempts"), ("geography", "Geography"),
              ("rep_shift", "Rep shift"), ("lead_source", "Lead source")]
    fig, axes = plt.subplots(1, 4, figsize=(13, 4.6), sharex=True)
    for ax, (col, title) in zip(axes, panels):
        t = s.groupby([col, "late"], observed=True)["joined"].agg(["size", "mean"]).unstack()
        t = t[(t[("size", True)] >= 20) & (t[("size", False)] >= 20)]
        y = np.arange(len(t))[::-1]
        e, l_ = t[("mean", False)] * 100, t[("mean", True)] * 100
        ax.hlines(y, l_, e, color=GRID, linewidth=2, zorder=1)
        ax.scatter(e, y, s=48, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=2,
                   label=f"≤{LATE_H}h")
        ax.scatter(l_, y, s=48, color=ORANGE, zorder=3, edgecolor=SURFACE, linewidth=2,
                   label=f">{LATE_H}h")
        ax.set_yticks(y, [str(i) for i in t.index], fontsize=8.5)
        ax.set_title(title, fontsize=10.5)
        ax.set_xlim(30, 100)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
        ax.grid(axis="y", visible=False)
    axes[0].legend(loc="lower left", frameon=False, fontsize=8.5)
    fig.suptitle("The 48h join-rate gap appears inside every subgroup", x=0.01, ha="left",
                 fontweight="bold", fontsize=13)
    fig.text(0.01, 0.9, "Join rate (J/S), demo within 48h (blue) vs later (orange). Subgroups "
             "with fewer than 20 demos on either side are hidden.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    path = FIG_DIR / "03_gap_effect_within_subgroups.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_post_demo(df):
    c = df[df["completed"]]
    overall = c["converted_f"].mean() * 100
    panels = [("geography", "By geography"), ("lead_source", "By lead source")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharex=True)
    for ax, (col, title) in zip(axes, panels):
        g = c.groupby(col)["converted_f"].agg(["sum", "size"])
        g["rate"] = g["sum"] / g["size"]
        g = g.sort_values("rate")
        y = np.arange(len(g))
        lo, hi = zip(*(wilson(k, n) for k, n in zip(g["sum"], g["size"])))
        flag = g.index.isin(["India", "Vietnam", "DSA"])
        cols = [ORANGE if f else BLUE for f in flag]
        ax.hlines(y, np.array(lo) * 100, np.array(hi) * 100, color=cols, linewidth=2)
        ax.scatter(g["rate"] * 100, y, s=52, color=cols, zorder=3, edgecolor=SURFACE, linewidth=2)
        ax.axvline(overall, color=TEXT_2, linewidth=1, linestyle=(0, (3, 3)))
        ax.set_yticks(y, [f"{i}  (n={n})" for i, n in zip(g.index, g["size"])], fontsize=8.5)
        ax.set_title(title, fontsize=10.5)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
        ax.grid(axis="y", visible=False)
    for ax in axes:
        ax.annotate(f"all: {overall:.1f}%", (overall, 1.0), xycoords=("data", "axes fraction"),
                    ha="center", va="bottom", fontsize=8, color=TEXT_2)
    fig.suptitle("Post-demo conversion (V/C) with 95% intervals", x=0.01, ha="left",
                 fontweight="bold", fontsize=13)
    fig.text(0.01, 0.89, "Leads who completed a demo (n=1,786). n = completed demos in the group. "
             "Orange = segments carried forward as candidate leaks.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    path = FIG_DIR / "04_post_demo_conversion.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- report

def compare_row(label, g1, g0, flag):
    t = two_prop(int(g1[flag].sum()), len(g1), int(g0[flag].sum()), len(g0))
    return [label, f"{len(g1):,}", pc(t["p1"]), f"{len(g0):,}", pc(t["p0"]), pp(t["diff"]),
            f"[{t['lo'] * 100:+.1f}, {t['hi'] * 100:+.1f}]", rel(t["p1"], t["p0"]), fmt_p(t["p"])]


COMPARE_COLS = ["comparison", "n", "rate", "n (comp.)", "rate (comp.)", "abs. diff",
                "95% CI (pp)", "rel. diff", "p"]


def main():
    csv = resolve_csv()
    df = prepare(load(csv))
    L = len(df)
    s = df[df["scheduled"]].copy()
    c = df[df["completed"]]
    months = df["created_at"].dt.to_period("M").nunique()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    seg, chi = screen(df)
    flagged = seg[(seg["p_holm"] < ALPHA) & (seg["diff"].abs() * 100 >= MIN_PP)]
    flagged = flagged.sort_values("p")

    early, late = s[~s["late"]], s[s["late"]]
    re_, rl = rates(early), rates(late)

    def seg_p(segment, step, col="p_holm"):
        return seg[(seg["seg"] == segment) & (seg["step"] == step)][col].iloc[0]

    def chi_p(dim, step):
        return chi[chi["dim"].str.contains(dim) & (chi["step"] == step)]["p_holm"].iloc[0]

    out = []
    w = out.append
    w("# Phase 3 — Find the Leak\n")
    w(f"Source file: `{csv.name}`  ")
    w("Generated by: `analysis/phase_03_leak_analysis.py` (re-run to reproduce).  ")
    w("Scope: where and for whom leads drop out. Three **candidate** leaks, not a final one. "
      "No solution and no ₹ sizing yet.\n")

    w("## 0. Summary\n")
    by_dim = flagged.groupby("dim").size()
    w(f"- **{len(seg)} segment-vs-rest comparisons** were run (6 dimensions × every segment × every "
      f"funnel step, plus the demo-timing dimension). After Holm correction for multiple testing and "
      f"a {MIN_PP:.0f} pp minimum difference, **{len(flagged)}** survive (section 3): "
      + "; ".join(f"{n} from {d.split('. ', 1)[1].lower()}" for d, n in by_dim.items()) + ". "
      "The follow-up survivor is explained by demo timing (section 6). That leaves two strong "
      "candidates and one weaker one:")
    w(f"  - **A. Demo booked more than {LATE_H}h after the lead arrived → no-show.** "
      f"{rl['S']:,} of {len(s):,} scheduled demos ({pc(rl['S'] / len(s))}) were booked >{LATE_H}h out. "
      f"Their join rate is {pc(rl['JS'])} vs {pc(re_['JS'])} for demos within {LATE_H}h "
      f"({pp(rl['JS'] - re_['JS'])}). The drop is a step at {LATE_H}h, not a slope, and it holds "
      "inside every follow-up, geography, shift, source and rep subgroup.")
    iv, rest_iv = c[c["india_vn"]], c[~c["india_vn"]]
    w(f"  - **B. India and Vietnam convert half as often after a completed demo.** "
      f"V/C {pc(iv['converted_f'].mean())} (n={len(iv):,}) vs {pc(rest_iv['converted_f'].mean())} "
      f"for the other six geographies (n={len(rest_iv):,}). Not explained by source, shift or demo timing. "
      f"India alone survives the strict screen (Holm p {fmt_p(seg_p('India', 'V/C'))}); Vietnam just "
      f"misses it (Holm p {fmt_p(seg_p('Vietnam', 'V/C'))}); geography as a whole clearly matters for V/C "
      f"(chi-square Holm p {fmt_p(chi_p('Geography', 'V/C'))}).")
    d1, d0 = c[c["dsa"]], c[~c["dsa"]]
    w(f"  - **C. DSA leads convert poorly after the demo.** V/C {pc(d1['converted_f'].mean())} "
      f"(n={len(d1)}) vs {pc(d0['converted_f'].mean())} for all other sources (raw p "
      f"{fmt_p(seg_p('DSA', 'V/C', 'p'))}). **Tentative:** it does not survive Holm across all "
      f"{len(seg)} comparisons (p {fmt_p(seg_p('DSA', 'V/C'))}), although lead source as a whole does "
      f"matter for V/C (chi-square Holm p {fmt_p(chi_p('Lead source', 'V/C'))}) and DSA is its lowest "
      "segment. Smaller sample and smaller volume than A and B.")
    w(f"- **No segment explains the largest raw drop-off** ({L - len(s):,} leads never scheduled). "
      "Scheduling rates are flat across source, geography and shift; rep differences do not survive "
      "correction.")
    w("- Rep shift, and parent-local demo hour under either clock assumption, show **no** "
      "meaningful effect on any step.\n")

    w("## 1. Method\n")
    w("- **Step rates** use the Phase 2 letters: S/L scheduled rate, J/S join rate, C/J completion "
      "rate, V/C post-demo conversion, V/L overall conversion. Each has its own denominator, so a "
      "segment's n shrinks at each step.")
    w("- **Comparison group** = every other lead in the same step's denominator (segment vs rest). "
      "This avoids picking a flattering comparison after looking at the data.")
    w("- **Test** = two-sided two-proportion z-test; 95% CI on the difference (Wald). Across the "
      f"{len(seg)} comparisons, p-values are **Holm-adjusted** (family-wise error 5%). Chi-square "
      "tests of \"does this dimension matter at all for this step\" are also Holm-adjusted (section 2.8).")
    w(f"- **Operationally meaningful** = Holm-adjusted p < {ALPHA} **and** |difference| ≥ {MIN_PP:.0f} pp. "
      "Both are needed: a big gap on 30 leads is noise, and a 1 pp gap on 3,000 leads is not worth acting on.")
    w("- **Parent timezone** is 1:1 with geography (Phase 1), so its table is shown but it is not "
      "tested a second time.")
    w(f"- **Time to demo** exists only for the {len(s):,} scheduled leads, so it has no S/L column. "
      "It is measured from `created_at` to `demo_scheduled_at`, i.e. to the **demo slot**, not to the "
      "moment the booking was made (the file has no booking timestamp).")
    w(f"- The data covers {months} months; per-month figures divide by {months}.")
    w("- These are **observational** differences. Nothing here shows that changing a segment's "
      "treatment would change its outcome.\n")

    # ---------------------------------------------------------------- 2. segment tables
    w("## 2. Funnel by segment\n")
    w("Columns: leads, then each step rate followed by the count that reached that step.\n")
    for col, label in DIMENSIONS:
        w(f"### 2.{label.split('.')[0]} {label.split('. ', 1)[1]}\n")
        if col == "gap_band":
            tbl = segment_table(s, col)
            tbl = tbl.drop(columns=["S/L", "S"]).rename(columns={"leads": "scheduled", "V/L": "V/S"})
            tbl.iloc[-1, 0] = "**All scheduled**"
            w(md_table(tbl))
            w(f"\nBase = the {len(s):,} scheduled leads, so the last column is V/S (conversions per "
              "scheduled lead), not V/L. Unscheduled leads have no demo time and cannot appear here.\n")
        else:
            w(md_table(segment_table(df, col)))
            if col == "parent_timezone":
                w("\nIdentical to geography row for row (each geography has exactly one timezone).")
            w("")

    w("### 2.8 Does each dimension matter at all? (chi-square, Holm-adjusted)\n")
    chi_t = chi.copy()
    chi_t["p"] = chi_t["p"].map(fmt_p)
    chi_t["p (Holm)"] = chi_t["p_holm"].map(fmt_p)
    chi_t["verdict"] = np.where(chi["p_holm"] < ALPHA, "**differs**", "no evidence")
    w(md_table(chi_t[["dim", "step", "groups", "n", "p", "p (Holm)", "verdict"]]
               .rename(columns={"dim": "dimension", "n": "leads in denominator"})))
    w("\nA chi-square test asks whether the step rate varies across the dimension's segments more "
      "than chance would. It does not say which segment is different.\n")

    # ---------------------------------------------------------------- 3. screen
    w("## 3. Every segment that stands out (unfiltered screen)\n")
    w(f"All segment-vs-rest comparisons with Holm p < {ALPHA} and |diff| ≥ {MIN_PP:.0f} pp, "
      f"sorted by p. This is the full list — nothing is left out.\n")
    ft = flagged.copy()
    w(md_table(pd.DataFrame({
        "dimension": ft["dim"], "segment": ft["seg"], "step": ft["step"],
        "n": ft["n"].map("{:,}".format), "rate": ft["p1"].map(pc), "rest n": ft["n0"].map("{:,}".format),
        "rest rate": ft["p0"].map(pc), "abs. diff": ft["diff"].map(pp),
        "rel. diff": [rel(a, b) for a, b in zip(ft["p1"], ft["p0"])],
        "p (Holm)": ft["p_holm"].map(fmt_p)})))
    near = seg[(seg["p"] < ALPHA) & ~seg.index.isin(flagged.index)].sort_values("p")
    w(f"\n**Near misses** — raw p < {ALPHA} but failing Holm or the {MIN_PP:.0f} pp bar "
      f"({len(near)} rows). Treat as unconfirmed:\n")
    w(md_table(pd.DataFrame({
        "dimension": near["dim"], "segment": near["seg"], "step": near["step"],
        "n": near["n"].map("{:,}".format), "rate": near["p1"].map(pc),
        "rest rate": near["p0"].map(pc), "abs. diff": near["diff"].map(pp),
        "p": near["p"].map(fmt_p), "p (Holm)": near["p_holm"].map(fmt_p)})))
    w("")

    # ---------------------------------------------------------------- 4. timing deep dive
    w(f"## 4. Demo timing: the {LATE_H}h step\n")
    w("### 4.1 Where the threshold comes from\n")
    scan = s.groupby(pd.cut(s["gap_h"], np.arange(0, 7 * 24 + 1, 6)), observed=True)["joined"] \
        .agg(["size", "mean"])
    scan_rows = [[f"{int(iv_.left)}–{int(iv_.right)}h", n, pc(m)] for iv_, (n, m) in
                 zip(scan.index, scan.itertuples(index=False))]
    w("Join rate in 6-hour bins of time-to-demo (first 7 days):\n")
    half = (len(scan_rows) + 1) // 2
    left, right = scan_rows[:half], scan_rows[half:] + [["", "", ""]] * (half - len(scan_rows[half:]))
    w(md_table(pd.DataFrame([l_ + r_ for l_, r_ in zip(left, right)],
                            columns=["gap", "demos", "join rate", "gap ", "demos ", "join rate "])))
    below, above = scan["mean"][:LATE_H // 6], scan["mean"][LATE_H // 6:]
    w(f"\nThe join rate sits at {below.min() * 100:.0f}–{below.max() * 100:.0f}% in every 6h bin up "
      f"to {LATE_H}h and at {above.min() * 100:.0f}–{above.max() * 100:.0f}% in every bin after it. "
      f"The threshold was chosen by looking at this table, so the {LATE_H}h cut itself is data-driven; "
      f"the gap between the two sides is too large (and too consistent bin-to-bin) to be a product "
      f"of where the line was drawn. The gap is also bimodal: demos ≤{LATE_H}h have a median of "
      f"{early['gap_h'].median():.0f}h; demos >{LATE_H}h a median of {late['gap_h'].median():.0f}h. "
      f"Very few fall near the line.\n")

    w(f"### 4.2 Early (≤{LATE_H}h) vs late (>{LATE_H}h) demos, every step\n")
    tbl = [compare_row(f"Join rate (J/S), >{LATE_H}h vs ≤{LATE_H}h", late, early, "joined"),
           compare_row("Completion rate (C/J)", late[late["joined"]], early[early["joined"]],
                       "completed"),
           compare_row("Post-demo conversion (V/C)", late[late["completed"]],
                       early[early["completed"]], "converted_f"),
           compare_row("Conversion per scheduled lead (V/S)", late, early, "converted_f")]
    w(md_table(pd.DataFrame(tbl, columns=COMPARE_COLS)))
    w(f"\nLate demos lose on joining but the leads who do join convert at least as well — "
      f"consistent with the late group being made of the same kind of parents, of whom fewer turn "
      f"up. Net effect on conversion per scheduled lead: {pp(rl['V'] / rl['S'] - re_['V'] / re_['S'])}.\n")

    w("### 4.3 Is it something else in disguise? (interactions and adjustment)\n")
    late_share = [[label.split(". ", 1)[1], ", ".join(
        f"{k}: {v * 100:.0f}%" for k, v in s.groupby(col, observed=True)["late"].mean().items())]
        for col, label in DIMENSIONS if col in ("lead_source", "geography", "rep_shift", "fu_band")]
    w("Share of scheduled demos booked >48h out, by segment:\n")
    w(md_table(pd.DataFrame(late_share, columns=["dimension", "share of demos > 48h"])))
    reps = s.groupby("rep_assigned")["late"].mean()
    w(f"\nBy rep the share ranges {reps.min() * 100:.0f}%–{reps.max() * 100:.0f}%. Late booking is "
      "spread evenly across source, geography, shift and rep. **Only follow-up attempts moves "
      "with it**: leads that took more attempts are far more often booked late.\n")
    rows = []
    for strata, label in [(["fu_band"], "follow-up attempts"),
                          (["fu_band", "geography", "rep_shift"], "follow-ups × geography × shift"),
                          (["fu_band", "rep_assigned", "lead_source"], "follow-ups × rep × source")]:
        d, k, n = mh_risk_diff(s, "late", "joined", strata)
        rows.append([label, k, f"{n:,}", pp(d)])
    rows.insert(0, ["none (raw)", 1, f"{len(s):,}", pp(rl["JS"] - re_["JS"])])
    w("Join-rate difference (late − early) after holding other variables fixed "
      "(Mantel-Haenszel weighted difference within strata):\n")
    w(md_table(pd.DataFrame(rows, columns=["held fixed", "strata used", "demos used",
                                           "late − early join rate"])))
    fu_gap = s.groupby(["fu_band", "late"], observed=True)["joined"].agg(["size", "mean"]).unstack()
    fu_gap = fu_gap[(fu_gap[("size", True)] >= 20) & (fu_gap[("size", False)] >= 20)]
    fu_d = (fu_gap[("mean", False)] - fu_gap[("mean", True)]) * 100
    w("\nThe difference barely moves when follow-ups, geography, shift, rep and source are held "
      f"fixed. Within each follow-up level with ≥20 demos on both sides, early demos are joined "
      f"{fu_d.min():.0f}–{fu_d.max():.0f} pp more often than late ones (chart 3).\n")

    after_end = s["demo_scheduled_at"] > df["created_at"].max()
    x = s[~after_end]
    w("Robustness checks:\n")
    rob = [compare_row(f"Excl. {int(after_end.sum())} demos dated after the last lead (Phase 2 §5)",
                       x[x["late"]], x[~x["late"]], "joined")]
    for m, g in s.groupby(s["created_at"].dt.to_period("M")):
        rob.append(compare_row(f"Leads created {m.strftime('%b %Y')} only", g[g["late"]],
                               g[~g["late"]], "joined"))
    w(md_table(pd.DataFrame(rob, columns=COMPARE_COLS)))
    w("")

    # ---------------------------------------------------------------- 5. post-demo geography
    w("## 5. Post-demo conversion: geography and lead source\n")
    w("### 5.1 India + Vietnam vs the other six geographies\n")
    tbl = [compare_row("V/C, India + Vietnam vs rest", iv, rest_iv, "converted_f"),
           compare_row("V/C, India vs rest", c[c["geography"] == "India"],
                       c[c["geography"] != "India"], "converted_f"),
           compare_row("V/C, Vietnam vs rest", c[c["geography"] == "Vietnam"],
                       c[c["geography"] != "Vietnam"], "converted_f")]
    ivl, restl = df[df["india_vn"]], df[~df["india_vn"]]
    for flag, denom, lab in STEPS[:3]:
        tbl.append(compare_row(f"{lab}, India + Vietnam vs rest", base(ivl, denom),
                               base(restl, denom), flag))
    w(md_table(pd.DataFrame(tbl, columns=COMPARE_COLS)))
    t_ivj = two_prop(int(base(ivl, "scheduled")["joined"].sum()), int(ivl["scheduled"].sum()),
                     int(base(restl, "scheduled")["joined"].sum()), int(restl["scheduled"].sum()))
    w(f"\nIndia and Vietnam schedule and complete at normal rates. Their join rate is "
      f"{abs(t_ivj['diff']) * 100:.1f} pp lower (raw p {fmt_p(t_ivj['p'])}; India and Vietnam "
      f"separately do not survive the section 3 screen on J/S). Most of the gap is after the demo. "
      f"Note the India + Vietnam grouping was formed after seeing the per-geography table, and its "
      f"comparison group includes the USA, which is itself above average "
      f"(V/C {pc(c[c['geography'] == 'USA']['converted_f'].mean())}).\n")
    inter = c.groupby(["lead_source", "india_vn"])["converted_f"].agg(["size", "mean"]).unstack()
    w("Interaction with lead source and rep shift (V/C, n in brackets):\n")
    irows = [[i, f"{inter.loc[i, ('mean', True)] * 100:.1f}% ({inter.loc[i, ('size', True)]})",
              f"{inter.loc[i, ('mean', False)] * 100:.1f}% ({inter.loc[i, ('size', False)]})"]
             for i in inter.index]
    sh = c.groupby(["rep_shift", "india_vn"])["converted_f"].agg(["size", "mean"]).unstack()
    irows += [[f"shift: {i}", f"{sh.loc[i, ('mean', True)] * 100:.1f}% ({sh.loc[i, ('size', True)]})",
               f"{sh.loc[i, ('mean', False)] * 100:.1f}% ({sh.loc[i, ('size', False)]})"]
              for i in sh.index]
    w(md_table(pd.DataFrame(irows, columns=["subgroup", "India + Vietnam", "other geographies"])))
    rows = [["none (raw)", pp(iv["converted_f"].mean() - rest_iv["converted_f"].mean())]]
    for strata, lab in [(["lead_source"], "lead source"),
                        (["lead_source", "rep_shift", "late"], "source × shift × demo >48h"),
                        (["rep_assigned", "fu_band"], "rep × follow-ups")]:
        rows.append([lab, pp(mh_risk_diff(c, "india_vn", "converted_f", strata)[0])])
    w("\nV/C difference (India + Vietnam − rest) with other variables held fixed:\n")
    w(md_table(pd.DataFrame(rows, columns=["held fixed", "difference"])))
    w("\nThe gap is present in every source and every shift and does not shrink on adjustment. "
      "Leads are routed to shifts regardless of geography (Phase 1 §5: every geography is split "
      "~42/15/43 across IST/SEA/US), and the India/Vietnam gap is the same whichever shift handles them.\n")

    w("### 5.2 DSA vs other lead sources\n")
    tbl = [compare_row("V/C, DSA vs all other sources", d1, d0, "converted_f"),
           compare_row("V/C, DSA vs rest — excl. India & Vietnam", d1[~d1["india_vn"]],
                       d0[~d0["india_vn"]], "converted_f"),
           compare_row("V/C, Affiliate vs all other sources", c[c["lead_source"] == "Affiliate"],
                       c[c["lead_source"] != "Affiliate"], "converted_f"),
           compare_row("V/C, Affiliate vs rest — excl. India & Vietnam",
                       c[(c["lead_source"] == "Affiliate") & ~c["india_vn"]],
                       c[(c["lead_source"] != "Affiliate") & ~c["india_vn"]], "converted_f"),
           compare_row("V/C, Referral + Organic vs rest", c[c["lead_source"].isin(["Referral", "Organic"])],
                       c[~c["lead_source"].isin(["Referral", "Organic"])], "converted_f")]
    dl, dr = df[df["dsa"]], df[~df["dsa"]]
    for flag, denom, lab in STEPS[:3]:
        tbl.append(compare_row(f"{lab}, DSA vs rest", base(dl, denom), base(dr, denom), flag))
    w(md_table(pd.DataFrame(tbl, columns=COMPARE_COLS)))
    dmh = mh_risk_diff(c, "dsa", "converted_f", ["geography", "rep_shift"])[0]
    w(f"\nDSA vs rest, V/C difference holding geography × shift fixed: {pp(dmh)}. "
      "DSA's gap is not a geography mix effect (DSA's geography mix matches every other source, "
      "Phase 1 §5). Affiliate's lower raw rate is not significant, and outside India and Vietnam it "
      "is at the average; its low figure comes from India/Vietnam Affiliate leads (section 5.1 "
      f"interaction table). Referral and Organic are the best sources but together are only "
      f"{df['lead_source'].isin(['Referral', 'Organic']).mean() * 100:.0f}% of leads.\n")

    # ---------------------------------------------------------------- 6. what showed nothing
    w("## 6. Checked and found no meaningful pattern\n")
    shift_r = df.groupby("rep_shift").apply(rates, include_groups=False)
    spread = {k: (shift_r.apply(lambda r: r[k]).max() - shift_r.apply(lambda r: r[k]).min()) * 100
              for k in ["SL", "JS", "VC"]}
    w(f"- **Rep shift**: across the three shifts S/L differs by at most {spread['SL']:.1f} pp, J/S by "
      f"{spread['JS']:.1f} pp and V/C by {spread['VC']:.1f} pp; smallest chi-square Holm p "
      f"{fmt_p(chi[chi.dim.str.contains('shift')]['p_holm'].min())} across its five steps. Completion rate is {pc(shift_r['IST_SHIFT']['CJ'])} on IST vs "
      f"{pc(shift_r['US_SHIFT']['CJ'])} on US (raw chi-square p = "
      f"{fmt_p(chi[(chi.dim.str.contains('shift')) & (chi.step == 'C/J')]['p'].iloc[0])}), "
      "not significant after correction.")
    w("- **Parent-local demo hour**. The storage clock is unknown (Phase 1 §7). Under either common "
      "assumption, demos in parent-local night-time do not have a lower join rate:\n")
    w(md_table(local_hour_check(s)))
    rep_s = df.groupby("rep_assigned")["scheduled"].mean()
    sl_all = pd.concat([df.groupby(col_)["scheduled"].mean() for col_ in
                        ["lead_source", "geography", "rep_assigned", "rep_shift"]])
    sl_min, sl_max = sl_all.min(), sl_all.max()
    s["fu4"] = s["fu_band"].eq("4")
    fu4_adj = mh_risk_diff(s, "fu4", "joined", ["late"])[0]
    w(f"\n- **Rep scheduling rate** ranges {rep_s.min() * 100:.1f}% ({rep_s.idxmin()}) to "
      f"{rep_s.max() * 100:.1f}% ({rep_s.idxmax()}). The chi-square raw p = "
      f"{fmt_p(chi[(chi.dim.str.contains('Rep assigned')) & (chi.step == 'S/L')]['p'].iloc[0])} fails "
      "Holm, and the reps with the lowest scheduling rates (AD-03, AD-12) have the highest post-demo "
      "conversion, so their overall V/L is above average. This looks more like a qualification "
      "trade-off than a leak.")
    w("- **The never-scheduled group (1,771 leads, 35%)** is the largest raw drop-off, but no "
      f"dimension in the file separates it: S/L is {sl_min * 100:.0f}–{sl_max * 100:.0f}% in every "
      "segment of every dimension (follow-up bands aside, see next point). "
      "Whatever drives it is not captured by these columns.")
    fu = df.groupby("fu_band", observed=True)["scheduled"].mean()
    w(f"- **Follow-up attempts**: S/L falls from {pc(fu.iloc[0])} at 0 attempts to "
      f"{pc(fu.loc['5'])} at 5. This is almost certainly reverse causality — reps keep trying the "
      "leads that are hard to book — so it is not evidence that follow-ups hurt. The count's "
      "definition and timing are unknown (Phase 1 open question 4); it may be recorded after the demo "
      f"was booked. The one follow-up band in the section 3 screen (4 attempts, J/S "
      f"{pp(seg[(seg.seg == '4') & (seg.step == 'J/S')]['diff'].iloc[0])} vs rest) shrinks to "
      f"{pp(fu4_adj)} once demo timing (≤/>{LATE_H}h) is held fixed: 70% of those demos are late.\n")

    # ---------------------------------------------------------------- 7. candidates
    w("## 7. The three strongest candidate leaks\n")
    w("Ranked by strength of evidence × volume. None is called the final leak here. \"Implied "
      "conversions\" is an **upper bound** that assumes the gap is fully causal and fully closable — "
      "an assumption not tested in this phase. It is shown only to compare scale between candidates.\n")

    extra_join_only = rl["S"] * (re_["JS"] - rl["JS"]) * rl["CJ"] * rl["VC"]
    extra_cohort = rl["S"] * (re_["V"] / re_["S"] - rl["V"] / rl["S"])
    extra_iv = len(iv) * (rest_iv["converted_f"].mean() - iv["converted_f"].mean())
    extra_dsa = len(d1) * (d0["converted_f"].mean() - d1["converted_f"].mean())
    t_late = two_prop(rl["J"], rl["S"], re_["J"], re_["S"])
    t_iv = two_prop(int(iv["converted_f"].sum()), len(iv), int(rest_iv["converted_f"].sum()), len(rest_iv))
    t_dsa = two_prop(int(d1["converted_f"].sum()), len(d1), int(d0["converted_f"].sum()), len(d0))

    cand = pd.DataFrame([
        ["Sample", f"{rl['S']:,} demos booked >48h", f"{len(iv):,} completed demos (India 186, Vietnam 278)",
         f"{len(d1)} completed DSA demos"],
        ["Passes strict screen (Holm, ≥5 pp)?",
         f"Yes — {int((flagged.dim.str.startswith('7.')).sum())} of {len(GAP_LABELS)} gap bands",
         f"India yes (p {fmt_p(seg_p('India', 'V/C'))}); Vietnam near miss (p {fmt_p(seg_p('Vietnam', 'V/C'))})",
         f"No (p {fmt_p(seg_p('DSA', 'V/C'))}); source-level chi-square yes"],
        ["Step affected", "Join (J/S)", "Post-demo conversion (V/C)", "Post-demo conversion (V/C)"],
        ["Actual performance", pc(t_late["p1"]), pc(t_iv["p1"]), pc(t_dsa["p1"])],
        ["Comparison group", f"{re_['S']:,} demos ≤48h: {pc(t_late['p0'])}",
         f"{len(rest_iv):,} other geos: {pc(t_iv['p0'])}", f"{len(d0):,} other sources: {pc(t_dsa['p0'])}"],
        ["Absolute difference", pp(t_late["diff"]), pp(t_iv["diff"]), pp(t_dsa["diff"])],
        ["95% CI", f"[{t_late['lo'] * 100:+.1f}, {t_late['hi'] * 100:+.1f}] pp",
         f"[{t_iv['lo'] * 100:+.1f}, {t_iv['hi'] * 100:+.1f}] pp",
         f"[{t_dsa['lo'] * 100:+.1f}, {t_dsa['hi'] * 100:+.1f}] pp"],
        ["Relative difference", rel(t_late["p1"], t_late["p0"]), rel(t_iv["p1"], t_iv["p0"]),
         rel(t_dsa["p1"], t_dsa["p0"])],
        ["p (raw)", fmt_p(t_late["p"]), fmt_p(t_iv["p"]), fmt_p(t_dsa["p"])],
        ["Survives adjustment", "Yes — follow-ups, geo, shift, rep, source",
         "Yes — source, shift, demo timing, rep", "Yes — geography × shift"],
        ["Implied extra conversions (upper bound, 2 months)",
         f"{extra_cohort:.0f}–{extra_join_only:.0f}", f"{extra_iv:.0f}", f"{extra_dsa:.0f}"],
        ["Per month", f"{extra_cohort / months:.0f}–{extra_join_only / months:.0f}",
         f"{extra_iv / months:.0f}", f"{extra_dsa / months:.0f}"],
        ["Operational lever exists?", "Plausibly — booking-window / reminder process",
         "Unclear — may be price/market fit", "Plausibly — channel mix / DSA handling"],
    ], columns=["", "A. Demo booked >48h out", "B. India + Vietnam post-demo", "C. DSA post-demo"])
    w(md_table(cand))
    w(f"\nImplied-conversion formulas: A low = late demos × (early V/S − late V/S); A high = late "
      f"demos × (early J/S − late J/S) × late C/J × late V/C. B = India/Vietnam completed × "
      f"(rest V/C − India/Vietnam V/C). C = DSA completed × (rest V/C − DSA V/C). "
      f"For scale: the whole file has {int(df['converted_f'].sum())} conversions "
      f"({int(df['converted_f'].sum()) / months:.0f}/month).\n")

    w(f"### A. Demo booked more than {LATE_H}h after lead creation\n")
    w(f"- **Pattern.** {pc(rl['S'] / len(s))} of scheduled demos are set >48h out. They lose "
      f"{abs(t_late['diff']) * 100:.0f} pp of join rate — the largest single effect in the file, on "
      "the second-largest drop-off (no-shows, 1,169 leads).")
    w("- **Why it is strong.** A clean step at 48h rather than a gradual slope; present in every "
      "subgroup; barely changes after adjustment; stable across June and July and after removing "
      "demos dated past the data window. p is far below any threshold.")
    w("- **Why it might not be what it looks like.**")
    w("  - *Selection / reverse causality:* a late slot may be a symptom, not a cause. Parents who are "
      "less keen may choose a far-away slot or be hard to reach (they needed more follow-ups). "
      "Holding follow-ups fixed does not remove the gap, but intent itself is not in the data.")
    w("  - *Slot availability:* late slots may reflect demo-teacher capacity, not the parent's choice. "
      "The file cannot tell who picked the slot.")
    w("  - *Definition:* `demo_scheduled_at` is the demo time, not the booking time. A demo booked "
      "within 1h for a slot 4 days away counts as \"late\". The effect is about the wait before the "
      "demo, not about how fast reps respond.")
    w("  - *Reschedules:* if a rescheduled demo overwrites the timestamp, late demos may partly be "
      "rescheduled ones, which have their own higher no-show risk.")
    w("  - *Post-demo offset:* late joiners convert slightly better (V/C), so the net loss per "
      "scheduled lead is smaller than the join-rate gap suggests (hence the range above).\n")

    w("### B. India and Vietnam: post-demo conversion\n")
    w(f"- **Pattern.** V/C {pc(t_iv['p1'])} vs {pc(t_iv['p0'])}. Up to the demo these markets look "
      "normal; the whole gap is at the payment decision.")
    w(f"- **Why it is strong.** Large ({pp(t_iv['diff'])}, about half the rate), present in every "
      "source and every shift, unchanged by adjustment. Geography is the only dimension other than "
      "demo timing whose effect survives every test in the file.")
    w("- **Caveat on strength.** India passes the strict screen on its own; Vietnam narrowly misses; "
      "the two were pooled after looking at the data.")
    w("- **Why it might not be what it looks like.**")
    w("  - *Price / purchasing power:* ₹60,000 is a much larger share of household income in India and "
      "Vietnam. That is a pricing or market question, not a sales-process leak.")
    w("  - *Product-market fit / language:* curriculum, language or payment-method fit may differ. The "
      "file has no field for any of these.")
    w("  - *Revenue per conversion may differ by market:* the ₹60,000 average may not apply, which "
      "changes the value of closing this gap.")
    w("  - *Operational version:* it could be the demo or the sales pitch that fails for these "
      "markets. Shift does not matter, but the individual teacher or closer is not in the data.\n")

    w("### C. DSA lead source: post-demo conversion\n")
    w(f"- **Pattern.** V/C {pc(t_dsa['p1'])} vs {pc(t_dsa['p0'])}; DSA leads schedule, join and "
      "complete normally.")
    w(f"- **Why it is weaker than A and B.** It fails the strict multiple-testing screen, so it may "
      f"be a chance finding among {len(seg)} comparisons. Only {len(d1)} completed demos and "
      f"{int(d1['converted_f'].sum())} conversions; the CI is wide ({t_dsa['lo'] * 100:+.1f} to {t_dsa['hi'] * 100:+.1f} pp); the implied volume is small.")
    w("- **Why it might not be what it looks like.**")
    w("  - *Lead quality by design:* \"DSA\" is undefined (Phase 1 open question 5). If it is a "
      "direct-sales or aggregator channel, lower intent may be the expected trade-off for cheaper leads.")
    w("  - *Cost per lead:* the ₹900 blended CAC hides channel differences. DSA could still be "
      "profitable per rupee spent.")
    w("  - *Attribution:* DSA leads may have been touched by another channel that the source field "
      "does not record.\n")

    w("## 8. Charts\n")
    figs = [chart_heatmap(df), chart_gap(s), chart_gap_strata(s), chart_post_demo(df)]
    captions = ["Step rates by segment vs the all-lead rate",
                "Join rate by time from lead creation to demo",
                "Early vs late join rate inside each subgroup",
                "Post-demo conversion by geography and source, with 95% intervals"]
    for f, cap in zip(figs, captions):
        w(f"![{cap}]({f.relative_to(OUT_PATH.parent).as_posix()})\n")

    w("## 9. Verification performed by the script\n")
    w("- Phase 2 stage counts reproduce (5,000 / 3,229 / 2,060 / 1,786 / 362)")
    w("- Each dimension's segment counts sum to the step total they are drawn from")
    w("- Early + late demos = scheduled leads; no scheduled lead has a missing or negative gap")
    w("- The Holm-adjusted p-values are ≥ the raw ones and monotone in rank\n")

    w("## 10. Open questions this phase adds\n")
    w("- Does `demo_scheduled_at` get overwritten on reschedule? Is there a booking timestamp?")
    w("- Who picks the demo slot — the parent, the rep, or a calendar with limited capacity?")
    w("- Is revenue per conversion (₹60,000) the same in India and Vietnam as elsewhere?")
    w("- What is DSA, and what does a DSA lead cost?")

    # ---------------------------------------------------------------- checks
    counts = stage_counts(df)
    if len(sys.argv) == 1:
        assert counts == [5000, 3229, 2060, 1786, 362], counts
    for col, _ in DIMENSIONS:
        src = s if col == "gap_band" else df
        assert src.groupby(col, observed=True).size().sum() == len(src), col
    assert len(early) + len(late) == len(s) and s["gap_h"].notna().all() and (s["gap_h"] > 0).all()
    ordered = seg.sort_values("p")
    assert (seg["p_holm"] >= seg["p"] - 1e-12).all() and ordered["p_holm"].is_monotonic_increasing
    assert L == counts[0]

    OUT_PATH.write_text("\n".join(out) + "\n")
    print(f"Comparisons: {len(seg)}; flagged: {len(flagged)}")
    print(flagged[["dim", "seg", "step", "n", "p1", "p0", "diff", "p_holm"]].to_string())
    print(f"Late demos: {rl['S']} join {rl['JS']:.3f} vs early {re_['S']} join {re_['JS']:.3f}")
    print(f"Wrote {OUT_PATH}")
    for f in figs:
        print(f"Wrote {f}")


if __name__ == "__main__":
    main()
