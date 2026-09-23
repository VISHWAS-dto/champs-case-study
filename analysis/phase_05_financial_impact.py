"""Phase 5 - Put a rupee value on the validated leak from Phase 4.

Leak (Phase 4, candidate A): demos booked more than 48h after the lead arrived are joined far less
often (46.9% vs 74.9%). This script builds a counterfactual - "what if those late demos had been
joined at the <=48h rate, and the extra joiners then behaved like <=48h joiners" - and converts the
extra customers into revenue with the assignment's Rs 60,000 per customer. The Rs 900 cost per lead
is used for the marketing lens (spend, CAC, cost of buying the same customers), never subtracted
from the counterfactual, because fixing the leak does not require buying any leads.

Every number in the report is printed next to the formula that produced it, so it can be checked
by hand.

Usage:
    python3 analysis/phase_05_financial_impact.py [path/to/csv]

Writes:
    results/phase_05_financial_impact.md
    results/figures/phase_05/*.png
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.dont_write_bytecode = True  # importing earlier phases should not leave __pycache__ behind
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase_02_funnel_analysis import load, resolve_csv, stage_counts  # noqa: E402
from phase_03_leak_analysis import BLUE, GRID, LATE_H, ORANGE, SURFACE, TEXT, TEXT_2, prepare  # noqa: E402
from phase_04_leak_validation import ASCII_CELL, NUM_RE, newcombe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "results" / "phase_05_financial_impact.md"
FIG_DIR = ROOT / "results" / "figures" / "phase_05"

# Given by the assignment.
REV_PER_CUSTOMER = 60_000  # Rs, average revenue per converted customer
COST_PER_LEAD = 900        # Rs, blended marketing cost per lead
MONTHS = 2                 # dataset period

# Modelling choices (stated as assumptions in the report).
CAUSAL_SHARES = [0.25, 0.50, 0.75, 1.00]  # share of the observed join gap that a fix would recover
PLANNING_SHARE = 0.50                     # the share used for the headline "modeled" figure


# --------------------------------------------------------------------------- formatting

def inr(x):
    """Indian digit grouping: 3552000 -> Rs 35,52,000."""
    neg, x = x < 0, abs(round(x))
    s = str(x)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return ("-" if neg else "") + "₹" + s


def lakh(x):
    return f"₹{x / 1e5:,.2f} lakh"


def pc(x, places=1):
    return f"{x * 100:.{places}f}%"


def pp(x):
    return f"{x * 100:+.1f} pp"


def f1(x):
    return f"{x:,.1f}"


def md_table(frame, right=()):
    """Phase 4's padded markdown table, but rupee amounts ("Rs 35,44,047", "Rs 7.79 lakh") also count as
    numbers, so money columns are right-aligned like counts and rates. Columns named in `right` are
    right-aligned regardless (value columns that mix numbers with ranges)."""
    cols = [str(c).translate(ASCII_CELL) for c in frame.columns]
    rows = [[str(v).translate(ASCII_CELL) for v in row] for row in frame.itertuples(index=False)]

    def is_num(x):
        x = x.strip("*")
        x = x[3:] if x.startswith("Rs ") else x
        return bool(NUM_RE.match(x.removesuffix(" lakh")))
    numeric = []
    for i in range(len(cols)):
        cells = [r[i] for r in rows if r[i] not in ("", "-")]
        numeric.append(frame.columns[i] in right or (bool(cells) and all(is_num(x) for x in cells)))
    widths = [max(3, len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]

    def fmt(cells):
        return "| " + " | ".join(cell.rjust(w) if num else cell.ljust(w)
                                 for cell, w, num in zip(cells, widths, numeric)) + " |"
    sep = "| " + " | ".join(("-" * (w - 1) + ":") if num else "-" * w for w, num in zip(widths, numeric)) + " |"
    return "\n".join([fmt(cols), sep, *(fmt(r) for r in rows)])


# --------------------------------------------------------------------------- model

def funnel(g):
    """Counts and step rates for a group of scheduled demos."""
    n, j, c, v = len(g), int(g["joined"].sum()), int(g["completed"].sum()), int(g["converted_f"].sum())
    return dict(n=n, j=j, c=c, v=v, js=j / n, cj=c / j, vc=v / c, vj=v / j, vs=v / n)


def counterfactual(n_late, gap, share, cj, vc):
    """Extra joins, completions and customers if `share` of a `gap` (pp, as a fraction) in join rate
    were recovered on `n_late` demos, with recovered joiners completing at `cj` and converting at `vc`."""
    joins = n_late * gap * share
    comps = joins * cj
    cust = comps * vc
    return dict(joins=joins, comps=comps, cust=cust, rev=cust * REV_PER_CUSTOMER)


# --------------------------------------------------------------------------- charts
# Same surface/text/grid and categorical slots 1-2 as Phases 3-4 (rcParams come from the Phase 3 import).
# Blue = observed, orange = modeled; the sensitivity grid is one sequential hue (blue).

def chart_funnel(late, ceil):
    """Late demos: observed funnel vs the counterfactual at the <=48h rates (ceiling)."""
    stages = ["Scheduled", "Joined", "Completed", "Converted"]
    actual = [late["n"], late["j"], late["c"], late["v"]]
    model = [late["n"], late["j"] + ceil["joins"], late["c"] + ceil["comps"], late["v"] + ceil["cust"]]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    y = np.arange(len(stages))[::-1]
    h = 0.36
    ax.barh(y + h / 2 + 0.01, actual, h, color=BLUE, label="Observed", edgecolor=SURFACE, linewidth=2)
    ax.barh(y - h / 2 - 0.01, model, h, color=ORANGE, label="Counterfactual (ceiling)",
            edgecolor=SURFACE, linewidth=2)
    top = max(model)
    for yi, a, m in zip(y, actual, model):
        ax.text(a + top * 0.01, yi + h / 2, f"{a:,.0f}", va="center", fontsize=9, color=TEXT)
        extra = f"   +{m - a:,.0f}" if m - a > 0.5 else ""
        ax.text(m + top * 0.01, yi - h / 2, f"{m:,.0f}{extra}", va="center", fontsize=9, color=TEXT,
                fontweight="bold" if extra else "normal")
    ax.set_yticks(y, stages)
    ax.set_xlim(0, top * 1.18)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.suptitle(f"Demos booked >{LATE_H}h out: observed vs joined at the <={LATE_H}h rate", x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.text(0.01, 0.875, f"{late['n']:,} late demos, Jun-Jul 2026. Counterfactual: join rate "
             f"{late['js'] * 100:.1f}% -> baseline, later steps at baseline rates. "
             f"+{ceil['cust']:.0f} customers x Rs 60,000 = Rs {ceil['rev'] / 1e5:.2f} lakh.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    path = FIG_DIR / "01_late_demo_counterfactual_funnel.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_money(actual_rev, spend, ceil, plan):
    """Monthly rupee figures, observed vs modeled, on one axis (all Rs lakh per month)."""
    rows = [("Actual revenue", actual_rev, "observed"),
            ("Marketing spend (Rs 900 x leads)", spend, "observed"),
            ("Potential opportunity (ceiling)", ceil["rev"], "modeled"),
            ("Modeled incremental (planning)", plan["rev"], "modeled")]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(rows))[::-1]
    vals = [r[1] / MONTHS / 1e5 for r in rows]
    for yi, (label, _, kind), v in zip(y, rows, vals):
        ax.barh(yi, v, 0.56, color=BLUE if kind == "observed" else ORANGE, edgecolor=SURFACE, linewidth=2,
                hatch="//" if kind == "modeled" else None)
        ax.text(v + max(vals) * 0.01, yi, f"Rs {v:,.2f} lakh", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, max(vals) * 1.18)
    ax.set_xlabel("Rs lakh per month")
    ax.grid(axis="y", visible=False)
    fig.suptitle("Monthly figures: what happened vs what the leak might be worth", x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.text(0.01, 0.875, "Blue = observed (x given Rs values). Orange hatched = modeled, not lost revenue. "
             "Actual financial loss: not established.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    path = FIG_DIR / "02_monthly_money.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_sensitivity(late, early, gaps, highlight):
    """Monthly modeled revenue for each gap x causal-share combination."""
    z = np.array([[counterfactual(late["n"], g, sh, early["cj"], early["vc"])["rev"] / MONTHS / 1e5
                   for sh in CAUSAL_SHARES] for _, g in gaps])
    fig, ax = plt.subplots(figsize=(9, 3.9))
    ax.imshow(z, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("seq", ["#e3eefb", BLUE]),
              aspect="auto", vmin=0, vmax=z.max())
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            dark = z[i, j] > z.max() * 0.62
            ax.text(j, i, f"Rs {z[i, j]:.2f} L", ha="center", va="center", fontsize=10,
                    color=SURFACE if dark else TEXT, fontweight="bold" if (i, j) in highlight else "normal")
    for (i, j), tag in highlight.items():
        ax.add_patch(plt.Rectangle((j - 0.48, i - 0.46), 0.96, 0.92, fill=False, edgecolor=ORANGE, linewidth=2.5))
        ax.text(j, i + 0.3, tag, ha="center", va="center", fontsize=8,
                color=SURFACE if z[i, j] > z.max() * 0.62 else TEXT_2)
    ax.set_xticks(range(len(CAUSAL_SHARES)), [f"{int(s * 100)}% causal" for s in CAUSAL_SHARES])
    ax.set_yticks(range(len(gaps)), [f"{lab}\n({g * 100:.1f} pp)" for lab, g in gaps])
    ax.tick_params(length=0)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.suptitle("Sensitivity: modeled revenue per month (Rs lakh)", x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.text(0.01, 0.86, "Rows: join-rate gap used. Columns: share of the gap a fix would recover (A8, a judgment).",
             fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    path = FIG_DIR / "03_sensitivity.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    csv = Path(sys.argv[1]) if len(sys.argv) > 1 else resolve_csv()
    df = prepare(load(csv))
    counts = stage_counts(df)
    assert counts == [5000, 3229, 2060, 1786, 362], counts  # Phase 2 funnel

    s = df[df["scheduled"]]
    late, early = funnel(s[s["late"]]), funnel(s[~s["late"]])
    assert (late["n"], late["j"], early["n"], early["j"]) == (1285, 603, 1944, 1457)  # Phase 4
    assert df.loc[~df["completed"], "converted_f"].sum() == 0  # every customer completed a demo

    gap, gap_lo, gap_hi = newcombe(early["j"], early["n"], late["j"], late["n"])  # baseline - late, >0
    band = s[(s["gap_h"] > 24) & (s["gap_h"] <= LATE_H)]
    band_js = band["joined"].mean()

    leads, customers = counts[0], counts[4]
    v_l = customers / leads
    actual_rev = customers * REV_PER_CUSTOMER
    spend = leads * COST_PER_LEAD
    cac = spend / customers

    # Ceiling: the whole observed gap closes; recovered joiners behave like <=48h joiners.
    ceil = counterfactual(late["n"], gap, 1.0, early["cj"], early["vc"])
    # Planning case: lower CI bound of the gap, half of it causal.
    plan = counterfactual(late["n"], gap_lo, PLANNING_SHARE, early["cj"], early["vc"])
    # Upper sensitivity only: recovered joiners convert like the late joiners who did turn up.
    ceil_latevj = counterfactual(late["n"], gap, 1.0, late["cj"], late["vc"])

    # Per-month check with each month's own rates.
    month_rows = []
    for m, g in s.groupby(s["created_at"].dt.month):
        lm, em = funnel(g[g["late"]]), funnel(g[~g["late"]])
        cf = counterfactual(lm["n"], em["js"] - lm["js"], 1.0, em["cj"], em["vc"])
        month_rows.append([pd.Timestamp(2026, m, 1).strftime("%B"), f"{lm['n']:,}", pc(lm["js"]), pc(em["js"]),
                           pp(em["js"] - lm["js"]), f1(cf["joins"]), f1(cf["cust"]), inr(cf["rev"])])
        month_rows[-1].append(cf)
    month_sum = sum(r[-1]["rev"] for r in month_rows)

    # Marketing lens.
    spend_late = late["n"] * COST_PER_LEAD
    noshow_late = late["n"] - late["j"]
    cac_ceil = spend / (customers + ceil["cust"])
    cac_plan = spend / (customers + plan["cust"])
    leads_equiv_ceil = ceil["cust"] / v_l
    leads_equiv_plan = plan["cust"] / v_l

    # Sensitivity grid: gap (lower CI / point / upper CI) x causal share.
    grid = []
    for label, g_ in [("lower 95% CI", gap_lo), ("point estimate", gap), ("upper 95% CI", gap_hi)]:
        row = [f"{label} ({g_ * 100:.1f} pp)"]
        for sh in CAUSAL_SHARES:
            cf = counterfactual(late["n"], g_, sh, early["cj"], early["vc"])
            row.append(f"{cf['cust']:.1f} cust. / {lakh(cf['rev'] / MONTHS)}")
        grid.append(row)
    grid_t = md_table(pd.DataFrame(grid, columns=["join-rate gap used",
                                                  *[f"{int(sh * 100)}% causal" for sh in CAUSAL_SHARES]]),
                      right=[f"{int(sh * 100)}% causal" for sh in CAUSAL_SHARES])

    # ------------------------------------------------------------------ charts
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    gaps = [("lower 95% CI", gap_lo), ("point estimate", gap), ("upper 95% CI", gap_hi)]
    figs = [chart_funnel(late, ceil), chart_money(actual_rev, spend, ceil, plan),
            chart_sensitivity(late, early, gaps, {(0, CAUSAL_SHARES.index(PLANNING_SHARE)): "planning",
                                                  (1, len(CAUSAL_SHARES) - 1): "ceiling"})]
    fig_md = "\n\n".join(f"![{alt}](figures/phase_05/{p.name})" for alt, p in zip(
        [f"Late demos: observed funnel vs counterfactual at the <={LATE_H}h rates",
         "Monthly actual revenue, marketing spend and modeled opportunity",
         "Sensitivity of monthly modeled revenue to gap and causal share"], figs))

    # ------------------------------------------------------------------ verification
    checks = []
    assert abs(early["vj"] - early["cj"] * early["vc"]) < 1e-12
    checks.append("V/J of the <=48h group equals C/J x V/C (the two-step and one-step routes agree)")
    assert abs(ceil["cust"] - late["n"] * gap * early["vj"]) < 1e-9
    assert abs(late["n"] * early["js"] - late["j"] - ceil["joins"]) < 1e-9
    checks.append("Extra joins = 1,285 x (baseline - late rate) = (1,285 x baseline) - 603 actual joins")
    assert abs(month_sum - ceil["rev"]) / ceil["rev"] < 0.05
    checks.append(f"June + July computed separately ({inr(month_sum)}) is within 5% of the pooled "
                  f"two-month ceiling ({inr(ceil['rev'])})")
    assert abs((late["v"] + early["v"]) - customers) == 0
    checks.append("Late + early customers (123 + 239) = 362 = all customers (unscheduled leads never convert)")
    checks.append("Phase 2 stage counts reproduce (5,000 / 3,229 / 2,060 / 1,786 / 362)")

    # ------------------------------------------------------------------ report
    L, E = late, early
    current_t = md_table(pd.DataFrame([
        ["Scheduled demos", f"{L['n']:,}", f"{E['n']:,}", "count of rows with demo_scheduled_at"],
        ["Joined", f"{L['j']:,}", f"{E['j']:,}", "demo_joined = Y"],
        ["Completed", f"{L['c']:,}", f"{E['c']:,}", "demo_completed = Y"],
        ["Converted", f"{L['v']:,}", f"{E['v']:,}", "converted = Y"],
        ["Join rate J/S", pc(L["js"]), pc(E["js"]), "joined / scheduled"],
        ["Completion rate C/J", pc(L["cj"]), pc(E["cj"]), "completed / joined"],
        ["Conversion after demo V/C", pc(L["vc"]), pc(E["vc"]), "converted / completed"],
        ["Customers per joiner V/J", pc(L["vj"]), pc(E["vj"]), "converted / joined = C/J x V/C"],
        ["Customers per scheduled demo V/S", pc(L["vs"]), pc(E["vs"]), "converted / scheduled"],
        ["Revenue (Rs 60,000 each)", inr(L["v"] * REV_PER_CUSTOMER), inr(E["v"] * REV_PER_CUSTOMER),
         "converted x 60,000"],
    ], columns=["metric", f">{LATE_H}h (affected)", f"<={LATE_H}h (baseline)", "formula"]))

    steps_t = md_table(pd.DataFrame([
        ["1", "Current join rate (affected)", f"{L['j']} / {L['n']:,}", pc(L["js"], 2)],
        ["2", "Baseline join rate", f"{E['j']:,} / {E['n']:,}", pc(E["js"], 2)],
        ["3", "Difference (gap)", f"{pc(E['js'], 2)} - {pc(L['js'], 2)}", f"{gap * 100:.2f} pp"],
        ["4", "Affected leads", f"scheduled leads with demo > {LATE_H}h after created_at", f"{L['n']:,}"],
        ["5a", "Additional joined demos", f"{L['n']:,} x {gap:.4f}", f1(ceil["joins"])],
        ["5b", "Additional completed demos", f"{f1(ceil['joins'])} x {E['cj']:.4f} (baseline C/J)",
         f1(ceil["comps"])],
        ["5c", "Additional customers", f"{f1(ceil['comps'])} x {E['vc']:.4f} (baseline V/C)", f"{ceil['cust']:.2f}"],
        ["6", "Additional revenue", f"{ceil['cust']:.2f} x 60,000", inr(ceil["rev"])],
        ["7", "Two-month impact", "= step 6 (the data covers two months)", inr(ceil["rev"])],
        ["8", "Monthly impact", f"{inr(ceil['rev'])} / 2", inr(ceil["rev"] / MONTHS)],
    ], columns=["step", "item", "formula", "result"]))

    plan_t = md_table(pd.DataFrame([
        ["Join-rate gap used", "lower end of the 95% CI of the gap", f"{gap_lo * 100:.2f} pp"],
        ["Causal share recovered", "assumption (see A8)", pc(PLANNING_SHARE, 0)],
        ["Additional joined demos", f"{L['n']:,} x {gap_lo:.4f} x {PLANNING_SHARE}", f1(plan["joins"])],
        ["Additional completed demos", f"{f1(plan['joins'])} x {E['cj']:.4f}", f1(plan["comps"])],
        ["Additional customers", f"{f1(plan['comps'])} x {E['vc']:.4f}", f"{plan['cust']:.2f}"],
        ["Two-month revenue", f"{plan['cust']:.2f} x 60,000", inr(plan["rev"])],
        ["Monthly revenue", f"{inr(plan['rev'])} / 2", inr(plan["rev"] / MONTHS)],
    ], columns=["item", "formula", "result"]))

    month_t = md_table(pd.DataFrame([r[:-1] for r in month_rows],
                                    columns=["month (lead created)", "late demos", "late J/S", "baseline J/S",
                                             "gap", "extra joins", "extra customers", "extra revenue"]))

    mkt_t = md_table(pd.DataFrame([
        ["Total marketing spend (2 months)", f"{leads:,} leads x 900", inr(spend)],
        ["Marketing spend per month", f"{inr(spend)} / 2", inr(spend / MONTHS)],
        ["Spend on the affected (>48h) leads", f"{L['n']:,} x 900", inr(spend_late)],
        ["Spend on affected leads that did not join", f"{noshow_late:,} x 900", inr(noshow_late * COST_PER_LEAD)],
        ["Current CAC (marketing only)", f"{inr(spend)} / {customers}", inr(cac)],
        ["CAC if the ceiling were captured", f"{inr(spend)} / ({customers} + {ceil['cust']:.2f})", inr(cac_ceil)],
        ["CAC under the planning case", f"{inr(spend)} / ({customers} + {plan['cust']:.2f})", inr(cac_plan)],
        ["Lead-to-customer rate V/L", f"{customers} / {leads:,}", pc(v_l, 2)],
        ["Leads needed to buy the ceiling's extra customers", f"{ceil['cust']:.2f} / {v_l:.4f}",
         f"{leads_equiv_ceil:,.0f}"],
        ["... their marketing cost (2 months)", f"{leads_equiv_ceil:,.1f} x 900", inr(leads_equiv_ceil * COST_PER_LEAD)],
        ["Leads needed to buy the planning case's extra customers", f"{plan['cust']:.2f} / {v_l:.4f}",
         f"{leads_equiv_plan:,.0f}"],
        ["... their marketing cost (2 months)", f"{leads_equiv_plan:,.1f} x 900", inr(leads_equiv_plan * COST_PER_LEAD)],
    ], columns=["item", "formula", "result"]))

    classes_t = md_table(pd.DataFrame([
        ["Actual revenue", "Observed", f"{customers} customers x 60,000", inr(actual_rev),
         f"{inr(actual_rev / MONTHS)} / month. Real, but Rs 60,000 is an assumed average, not a booked figure."],
        ["Marketing acquisition cost", "Observed x given", f"{leads:,} leads x 900", inr(spend),
         f"{inr(spend / MONTHS)} / month. Already spent; the leak does not change it."],
        ["Potential revenue opportunity (ceiling)", "Modeled, upper bound",
         "full gap closed; 100% causal", inr(ceil["rev"]),
         f"{inr(ceil['rev'] / MONTHS)} / month. Only true if the whole gap is caused by booking delay."],
        ["Modeled incremental revenue (planning case)", "Modeled, conservative",
         "lower-CI gap x 50% causal", inr(plan["rev"]),
         f"{inr(plan['rev'] / MONTHS)} / month. The figure to plan with; the 50% is a judgment."],
        ["Actual financial loss", "Not established", "-", "-",
         "Not computable. See section 8. Needs causal proof, margin data and the cost of the fix."],
    ], columns=["category", "status", "basis", "two months", "note"]))

    summary_t = md_table(pd.DataFrame([
        ["Actual revenue (observed customers x Rs 60,000)", inr(actual_rev), inr(actual_rev / MONTHS)],
        ["Marketing spend (all leads x Rs 900)", inr(spend), inr(spend / MONTHS)],
        ["**Potential revenue opportunity** (ceiling, whole gap closed)", f"**{inr(ceil['rev'])}**",
         f"**{inr(ceil['rev'] / MONTHS)}**"],
        ["**Modeled incremental revenue** (planning case)", f"**{inr(plan['rev'])}**",
         f"**{inr(plan['rev'] / MONTHS)}**"],
        ["Actual financial loss", "-", "-"],
    ], columns=["what", "two months", "per month"]))
    summary_t += "\n\n\"-\" = not established (section 8)."

    assume_t = md_table(pd.DataFrame([
        ["A1", "Average revenue per converted customer = Rs 60,000, the same for every customer and segment.",
         "given", "Revenue scales 1:1 with this figure. If late-booked customers are worth less/more, adjust."],
        ["A2", "Blended marketing cost per lead = Rs 900, the same for every lead.", "given",
         "Changes marketing spend and CAC only, not the revenue opportunity."],
        ["A3", f"The dataset covers two months (leads created 1 June - 31 July 2026: {counts[0]:,} leads, "
               f"{month_rows[0][1]} and {month_rows[1][1]} late demos by month), so monthly = two-month / 2.",
         "given + checked", "Two months have near-identical volume (2,504 and 2,496 leads), so splitting evenly is fair."],
        ["A4", "Revenue is counted in the month the lead was created, and every `converted = Y` is a paying "
               "customer worth A1.", "choice", "Some July conversions may land in August; timing shifts, total does not."],
        ["A5", f"Baseline = demos booked within {LATE_H}h of lead creation, same dataset, same two months "
               f"(J/S {pc(E['js'])}).", "choice",
         f"A narrower comparison (24-{LATE_H}h, J/S {pc(band_js)}) would give a *larger* gap; the <={LATE_H}h "
         f"group is the more conservative choice."],
        ["A6", f"Extra joiners complete at the baseline C/J ({pc(E['cj'])}) and convert at the baseline V/C "
               f"({pc(E['vc'])}), i.e. {pc(E['vj'])} per joiner.", "choice",
         f"Late joiners who *did* turn up converted better ({pc(L['vj'])} per joiner). Using that would raise the "
         f"ceiling to {inr(ceil_latevj['rev'])}. It is not used: parents recovered by a fix are probably less "
         f"committed than those who showed up despite the wait."],
        ["A7", "Lead volume, source mix, rep capacity and the Rs 60,000 average stay the same; recovered demos do "
               "not displace other demos.", "choice",
         "If reps are at capacity, extra joins could crowd out other demos and the gain would be smaller. The "
         "file has no capacity data."],
        ["A8", "Only part of the observed gap is caused by the booking delay. The planning case uses **50%**.",
         "**judgment**",
         "Not estimable from the data. Phase 4: E-value 2.57 - an unmeasured confounder (parent intent) would "
         "need a risk ratio >=2.57 with both late booking and no-show to explain the whole gap. 50% is a round "
         "midpoint, not a measurement. Section 5 shows 25-100%."],
        ["A9", f"The planning case uses the lower end of the 95% CI of the gap ({gap_lo * 100:.1f} pp) instead "
               f"of the point estimate ({gap * 100:.1f} pp).", "choice", "Guards against sampling noise on top of A8."],
        ["A10", "Unscheduled leads, no-shows and non-completers never convert (true in the data: 0 conversions "
                "without a completed demo).", "checked", "-"],
        ["A11", "Revenue, not profit. No margin, delivery cost, refund or fix-cost data is available.",
         "limitation", "All figures are top-line."],
    ], columns=["#", "assumption", "type", "effect if wrong"]))

    items_t = md_table(pd.DataFrame([
        ["1", "Current performance (late J/S)", pc(L["js"])],
        ["2", f"Baseline performance (<={LATE_H}h J/S)", pc(E["js"])],
        ["3", "Difference", f"{gap * 100:.1f} pp"],
        ["", "... 95% CI of the difference", f"{gap_lo * 100:.1f} to {gap_hi * 100:.1f} pp"],
        ["4", "Affected leads", f"{L['n']:,}"],
        ["", "... share of scheduled demos / of all leads",
         f"{pc(L['n'] / counts[1])} / {pc(L['n'] / leads)}"],
        ["5", "Extra joined demos", f"{ceil['joins']:.0f}"],
        ["", "Extra completed demos", f"{ceil['comps']:.0f}"],
        ["", "Extra customers", f"{ceil['cust']:.1f}"],
        ["6", "Extra revenue", inr(ceil["rev"])],
        ["7", "Two-month impact", inr(ceil["rev"])],
        ["8", "Monthly impact", inr(ceil["rev"] / MONTHS)],
    ], columns=["#", "item", "value"]), right=("value",))

    text = f"""# Phase 5 — Financial Impact of the Validated Leak

Source file: `{csv.name}`
Generated by: `analysis/phase_05_financial_impact.py` (re-run to reproduce; no randomness).
Leak being sized: **Phase 4 candidate A — demos booked more than {LATE_H}h after the lead arrived are joined far less often.**
Candidates B and C are not sized here (B is not an operational leak on the evidence; C is weak). Adding them would also double-count leads.

## 0. Summary

{summary_t}

- **The counterfactual.** If the {L['n']:,} demos booked more than {LATE_H}h out had been joined at the same rate as demos booked within {LATE_H}h ({pc(E['js'])} instead of {pc(L['js'])}), and the extra joiners had then completed and converted like the within-{LATE_H}h joiners, the business would have had **~{ceil['joins']:.0f} more joined demos, ~{ceil['comps']:.0f} more completed demos and ~{ceil['cust']:.0f} more customers** in two months: **{lakh(ceil['rev'])} (≈{lakh(ceil['rev'] / MONTHS)} a month)**. That is +{pc(ceil['cust'] / customers)} on the {customers} customers actually won.
- **That is a ceiling, not a loss.** Phase 4 showed the association is strong but could not rule out that low-intent parents choose far-off slots. The planning case keeps only the lower end of the 95% CI of the gap and assumes half of it is caused by the delay: **~{plan['cust']:.0f} customers, {lakh(plan['rev'])} over two months (≈{lakh(plan['rev'] / MONTHS)} a month)**.
- **Where Rs 900 fits.** It is a sunk cost: the leads are already bought, and fixing the leak buys no new ones, so it is **not subtracted** from the opportunity. It matters in three ways: it gives the marketing spend ({inr(spend)}) and CAC ({inr(cac)} → {inr(cac_ceil)} at the ceiling); it prices the spend sitting on affected leads ({inr(spend_late)}); and it says what the same extra customers would cost to *buy* with more leads ({inr(leads_equiv_ceil * COST_PER_LEAD)} at the ceiling, {inr(leads_equiv_plan * COST_PER_LEAD)} in the planning case).
- **Actual financial loss cannot be established from this file** (section 8).

## 1. Assumptions

Every number below depends on these. Items marked *given* come from the assignment; the rest are choices made here.

{assume_t}

## 2. Current performance (step 1)

Base: {counts[1]:,} scheduled demos, split by whether the demo slot is more than {LATE_H}h after `created_at`.

{current_t}

Late demos lose at the **join** step. Once a parent joins, late demos do at least as well as early ones (C/J {pc(L['cj'])} vs {pc(E['cj'])}; V/C {pc(L['vc'])} vs {pc(E['vc'])}). So the counterfactual only changes the join rate, and carries the extra joiners through the *baseline's* later steps (the lower of the two; see A6).

## 3. Counterfactual — potential revenue opportunity (ceiling)

**Question:** what if the {L['n']:,} late demos had been joined at the baseline rate?

Formulas:

```
gap                 = J/S(baseline) - J/S(late)
extra joined        = N_late x gap
extra completed     = extra joined x C/J(baseline)
extra customers     = extra completed x V/C(baseline)      (= extra joined x V/J(baseline))
extra revenue (2mo) = extra customers x 60,000
monthly             = extra revenue (2mo) / 2
```

{steps_t}

Hand check: {L['n']:,} × ({E['j']:,}/{E['n']:,}) = {L['n'] * E['js']:,.2f} joins expected at the baseline rate; minus {L['j']} actual joins = {ceil['joins']:.2f} extra joins. {ceil['joins']:.2f} × ({E['v']}/{E['j']:,}) = {ceil['cust']:.2f} customers. {ceil['cust']:.2f} × 60,000 = {inr(ceil['rev'])}.

Items 1–8 requested:

{items_t}

**Month by month** (each month's own rates, 100% causal — a stability check on item 8):

{month_t}

June + July = {inr(month_sum)} vs {inr(ceil['rev'])} pooled; the small difference is because each month uses its own rates.

## 4. Modeled incremental revenue (planning case)

The ceiling assumes the entire {gap * 100:.1f} pp gap is caused by the delay and would disappear. Neither is shown. The planning case applies two haircuts (A8, A9):

```
extra customers = N_late x gap_lower_CI x causal_share x C/J(baseline) x V/C(baseline)
                = {L['n']:,} x {gap_lo:.4f} x {PLANNING_SHARE} x {E['cj']:.4f} x {E['vc']:.4f}
```

{plan_t}

## 5. Sensitivity

Extra customers and **monthly** revenue for each combination of join-rate gap and causal share (baseline C/J and V/C throughout):

{grid_t}

- The ceiling in section 3 is *point estimate × 100%*. The planning case in section 4 is *lower 95% CI × 50%*.
- Every cell is linear: monthly revenue = {L['n']:,} × gap × share × {E['vj']:.4f} × 60,000 / 2.
- Using the late joiners' own conversion per joiner ({pc(L['vj'])}) instead of the baseline's (A6) raises every cell by {pc(L['vj'] / E['vj'] - 1, 0)}; the ceiling would be {inr(ceil_latevj['rev'])} over two months.

## 6. Where the Rs 900 marketing cost is relevant

{mkt_t}

How to read it:

- **Not a cost of the counterfactual.** All {leads:,} leads, including the {L['n']:,} affected ones, were already paid for. Recovering their demos needs no new leads, so the modeled revenue is **not** reduced by Rs 900 × anything. (The real cost of a fix — rep time, reminders, calendar capacity — is not in the data and is not included.)
- **Not a loss either.** The {inr(spend_late)} spent on late-booked leads, or the {inr(noshow_late * COST_PER_LEAD)} on the ones who did not join, would have been spent anyway. Calling it "wasted" double-counts it with the revenue opportunity.
- **Efficiency.** Marketing-only CAC is {inr(cac)} today. The same spend spread over more customers would lower it to {inr(cac_ceil)} (ceiling) or {inr(cac_plan)} (planning case).
- **Price benchmark.** At today's lead-to-customer rate ({pc(v_l, 2)}), buying the ceiling's {ceil['cust']:.0f} extra customers through more leads would take ~{leads_equiv_ceil:,.0f} leads and {inr(leads_equiv_ceil * COST_PER_LEAD)} of marketing ({inr(leads_equiv_ceil * COST_PER_LEAD / MONTHS)}/month); the planning case's {plan['cust']:.0f} would take ~{leads_equiv_plan:,.0f} leads and {inr(leads_equiv_plan * COST_PER_LEAD)} ({inr(leads_equiv_plan * COST_PER_LEAD / MONTHS)}/month). That is the marketing budget a fix is equivalent to — it assumes extra leads convert at the average rate, which is optimistic for marginal spend.
- **Return on spend.** Revenue per rupee of marketing is {actual_rev / spend:.2f} today; {(actual_rev + ceil['rev']) / spend:.2f} at the ceiling; {(actual_rev + plan['rev']) / spend:.2f} in the planning case.

## 7. The five figures, kept apart

{classes_t}

- *Actual revenue* and *marketing cost* describe what happened.
- *Potential revenue opportunity* and *modeled incremental revenue* describe what might have happened. They are **not** revenue that was lost, and they must not be added to each other or to Phase 4 candidate B.
- The naive figure — {L['n'] - L['v']:,} non-converted late demos × 60,000 = {inr((L['n'] - L['v']) * REV_PER_CUSTOMER)} — is **not** used anywhere. Most of those parents would not have bought even with an early demo; in the baseline group only {pc(E['vs'])} of scheduled demos become customers.

## 8. Why actual financial loss cannot be established

1. **No proof of cause.** Phase 4 established a strong association, not causation (A8). Without a causal effect there is no "revenue we would otherwise have had".
2. **No observed counterfactual.** Nobody in the data had their late demo moved earlier; the baseline is a different group of parents.
3. **Revenue, not profit.** Rs 60,000 is revenue. A loss to the business is lost margin, and margin is not given (A11).
4. **Unknown fix cost and capacity.** If recovering those demos needs more rep hours or earlier slots that are already full (A7), the net gain is smaller than the revenue figure.
5. **Rs 60,000 is an average.** Whether late-booked customers are worth the same is not known (A1).

What *can* be said: over these two months the business made {inr(actual_rev)} of revenue on {inr(spend)} of marketing, and the booking-delay pattern is associated with a revenue opportunity of up to {inr(ceil['rev'])} ({inr(ceil['rev'] / MONTHS)} a month), with {inr(plan['rev'])} ({inr(plan['rev'] / MONTHS)} a month) as a conservative planning figure. Turning either into a *loss* needs a test (e.g. randomising some leads to a within-{LATE_H}h slot) plus margin and cost data.

## 9. Charts

__FIGS__

## 10. Verification performed by the script

""" + "\n".join(f"- {c}" for c in checks) + "\n"

    text = text.replace("__FIGS__", fig_md)
    OUT_PATH.write_text(text)
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print(f"ceiling {inr(ceil['rev'])} ({inr(ceil['rev'] / MONTHS)}/mo); planning {inr(plan['rev'])} "
          f"({inr(plan['rev'] / MONTHS)}/mo)")


if __name__ == "__main__":
    main()
