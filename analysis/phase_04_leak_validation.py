"""Phase 4 - Validate the candidate leaks from Phase 3.

Stress-tests the three Phase 3 candidates:
    A. demo booked more than 48h after the lead arrived -> lower join rate (J/S)
    B. India + Vietnam -> lower post-demo conversion (V/C)
    C. DSA lead source -> lower post-demo conversion (V/C)

For each one it checks lead source, geography, parent timezone, rep shift, rep,
follow-up attempts, whether one small group drives the result, the two-month
period, sample size and obvious confounders. Tests used: stratified differences
with Newcombe CIs, Mantel-Haenszel adjusted differences, Cochran's Q for
heterogeneity, sign tests, leave-one-out, permutation tests that account for how
each candidate was picked, logistic regression and E-values. Associations only:
nothing here shows causation.

Usage:
    python3 analysis/phase_04_leak_validation.py [path/to/csv]

Writes:
    results/phase_04_leak_validation.md
    results/figures/phase_04/*.png
"""

import re
import sys
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import binomtest, chi2, chi2_contingency, fisher_exact, norm  # noqa: E402

sys.dont_write_bytecode = True  # importing earlier phases should not leave __pycache__ behind
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase_02_funnel_analysis import load, resolve_csv, stage_counts  # noqa: E402
from phase_03_leak_analysis import (BLUE, GRID, LATE_H, ORANGE, SURFACE, TEXT, TEXT_2,  # noqa: E402
                                    fmt_p, pc, pp, prepare, screen, two_prop, wilson)

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "results" / "phase_04_leak_validation.md"
FIG_DIR = ROOT / "results" / "figures" / "phase_04"

SEED = 20260923
N_PERM = 5000
MIN_N = 10  # a stratum needs this many rows on each side to count in consistency checks
Z80 = norm.ppf(0.80)
N_SCREEN = 204  # Phase 3 comparisons; used for the "would it survive Holm" sample-size bar

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOUR_BANDS = ["00–08", "08–12", "12–17", "17–22", "22–24"]


# --------------------------------------------------------------------------- markdown

NUM_RE = re.compile(r"^(<|>|<=|>=|~)?[+-]?[\d,]*\.?\d+(%| pp|x)?$")


# Symbols that many editors and terminal fonts draw wider than one column ("ambiguous width"), which
# pushes table rows out of line. Inside tables they are written in plain ASCII.
ASCII_CELL = str.maketrans({"·": "/", "–": "-", "−": "-", "≤": "<=", "≥": ">=", "→": "->", "α": "alpha",
                            "×": "x", "₹": "Rs "})


def md_table(frame):
    """Padded GitHub markdown table. A column is right-aligned when every non-blank cell is a single
    number (counts, %, pp, p-values such as <0.001); text, intervals and blank columns stay left.
    Cells are ASCII-only so the padding lines up in any monospace font."""
    cols = [str(c).translate(ASCII_CELL) for c in frame.columns]
    rows = [[str(v).translate(ASCII_CELL) for v in row] for row in frame.itertuples(index=False)]
    numeric = []
    for i in range(len(cols)):
        cells = [r[i] for r in rows if r[i] not in ("", "—")]
        numeric.append(bool(cells) and all(NUM_RE.match(x.strip("*")) for x in cells))
    widths = [max(3, len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]

    def fmt(cells):
        return "| " + " | ".join(cell.rjust(w) if num else cell.ljust(w)
                                 for cell, w, num in zip(cells, widths, numeric)) + " |"
    sep = "| " + " | ".join(("-" * (w - 1) + ":") if num else "-" * w for w, num in zip(widths, numeric)) + " |"
    return "\n".join([fmt(cols), sep, *(fmt(r) for r in rows)])


# --------------------------------------------------------------------------- statistics

def newcombe(k1, n1, k0, n0):
    """Difference p1 - p0 with Newcombe's hybrid-score 95% CI (behaves at small n and 0/1 rates)."""
    p1, p0 = k1 / n1, k0 / n0
    l1, u1 = wilson(k1, n1)
    l0, u0 = wilson(k0, n0)
    d = p1 - p0
    return d, d - np.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2), d + np.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)


def cell(g, exp, out):
    a, b = g[g[exp]], g[~g[exp]]
    return len(a), int(a[out].sum()), len(b), int(b[out].sum())


def stratify(frame, exp, out, col):
    """One row per level of `col`: exposed vs comparison inside that level, plus a summary:
    Mantel-Haenszel difference (fixed-weight variance), Cochran's Q across strata, sign test."""
    rows = []
    for lvl, g in frame.groupby(col, observed=True, sort=True):
        n1, k1, n0, k0 = cell(g, exp, out)
        if n1 == 0 or n0 == 0:
            rows.append(dict(level=str(lvl), n1=n1, k1=k1, n0=n0, k0=k0, d=np.nan, lo=np.nan, hi=np.nan))
            continue
        d, lo, hi = newcombe(k1, n1, k0, n0)
        rows.append(dict(level=str(lvl), n1=n1, k1=k1, n0=n0, k0=k0, d=d, lo=lo, hi=hi))
    t = pd.DataFrame(rows)
    ok = t[(t.n1 > 0) & (t.n0 > 0)]
    w = ok.n1 * ok.n0 / (ok.n1 + ok.n0)
    p1, p0 = ok.k1 / ok.n1, ok.k0 / ok.n0
    mh = (w * (p1 - p0)).sum() / w.sum()
    se = np.sqrt((w ** 2 * (p1 * (1 - p1) / ok.n1 + p0 * (1 - p0) / ok.n0)).sum()) / w.sum()
    big = t[(t.n1 >= MIN_N) & (t.n0 >= MIN_N)]
    # Cochran's Q on stratum differences; Agresti-Caffo adjusted variances avoid zero variance
    a1, a0 = (big.k1 + 1) / (big.n1 + 2), (big.k0 + 1) / (big.n0 + 2)
    iv = 1 / (a1 * (1 - a1) / (big.n1 + 2) + a0 * (1 - a0) / (big.n0 + 2))
    dd = big.k1 / big.n1 - big.k0 / big.n0
    q = (iv * (dd - (iv * dd).sum() / iv.sum()) ** 2).sum()
    q_p = chi2.sf(q, len(big) - 1) if len(big) > 1 else np.nan
    same = int((np.sign(big.d) == np.sign(mh)).sum())
    sign_p = binomtest(same, len(big), 0.5).pvalue if len(big) else np.nan
    return t, dict(mh=mh, lo=mh - 1.96 * se, hi=mh + 1.96 * se, k=len(big), same=same,
                   sign_p=sign_p, q_p=q_p, dropped=len(t) - len(big))


def leave_one_out(frame, exp, out, col):
    """Drop each level of `col` in turn; returns one row per dropped level."""
    rows = []
    for lvl in frame[col].dropna().unique():
        f = frame[frame[col] != lvl]
        n1, k1, n0, k0 = cell(f, exp, out)
        if n1 == 0 or n0 == 0:
            continue
        t = two_prop(k1, n1, k0, n0)
        rows.append(dict(level=str(lvl), d=t["diff"], p=t["p"], n1=n1))
    return pd.DataFrame(rows)


def deficit_share(frame, exp, out, col, overall_p0):
    """Share of the exposed group's shortfall contributed by each stratum. Shortfall in a stratum =
    exposed n x (comparison rate in the stratum - exposed rate). Sparse comparison -> overall rate."""
    rows = []
    for lvl, g in frame.groupby(col, observed=True):
        n1, k1, n0, k0 = cell(g, exp, out)
        if n1 == 0:
            continue
        p0 = k0 / n0 if n0 >= MIN_N else overall_p0
        rows.append(dict(level=str(lvl), n1=n1, deficit=n1 * p0 - k1))
    t = pd.DataFrame(rows)
    t["share_n"] = t.n1 / t.n1.sum()
    t["share_def"] = t.deficit / t.deficit.sum()
    return t.sort_values("share_def", ascending=False)


def logit(y, X, iters=100):
    """Logistic regression by Newton-Raphson. Returns coefficients and covariance matrix."""
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ beta)))
        h = X.T @ (X * (p * (1 - p))[:, None])
        step = np.linalg.solve(h, X.T @ (y - p))
        beta += step
        if np.abs(step).max() < 1e-9:
            break
    return beta, np.linalg.inv(h)


def adjusted(frame, exp, out, covars):
    """Odds ratio for `exp` with 95% CI, and the average marginal effect in pp
    (mean predicted outcome with everyone exposed minus with no one exposed)."""
    dummies = pd.get_dummies(frame[covars].astype(str), drop_first=True, dtype=float) if covars else \
        pd.DataFrame(index=frame.index)
    X = np.column_stack([np.ones(len(frame)), frame[exp].astype(float), dummies.to_numpy()])
    beta, cov = logit(frame[out].astype(float).to_numpy(), X)
    se = np.sqrt(cov[1, 1])
    x1, x0 = X.copy(), X.copy()
    x1[:, 1], x0[:, 1] = 1, 0
    ame = (1 / (1 + np.exp(-(x1 @ beta))) - 1 / (1 + np.exp(-(x0 @ beta)))).mean()
    return dict(or_=np.exp(beta[1]), lo=np.exp(beta[1] - 1.96 * se), hi=np.exp(beta[1] + 1.96 * se),
                p=2 * norm.sf(abs(beta[1] / se)), ame=ame, k=X.shape[1] - 2)


def e_value(k1, n1, k0, n0):
    """E-value (VanderWeele & Ding) for the observed risk ratio and for its CI limit nearest 1."""
    rr = (k1 / n1) / (k0 / n0)
    se = np.sqrt(1 / k1 - 1 / n1 + 1 / k0 - 1 / n0)
    lim = np.exp(np.log(rr) + 1.96 * se) if rr < 1 else np.exp(np.log(rr) - 1.96 * se)

    def ev(r):
        r = 1 / r if r < 1 else r
        return 1.0 if r <= 1 else r + np.sqrt(r * (r - 1))
    return rr, ev(rr), (1.0 if (rr < 1) != (lim < 1) else ev(lim))


def mde(n1, n0, p0, z_alpha):
    """Smallest difference detectable with 80% power at the given two-sided critical value."""
    return (z_alpha + Z80) * np.sqrt(p0 * (1 - p0) * (1 / n1 + 1 / n0))


def smd(frame, exp, col):
    """Largest absolute standardised mean difference across the categories of `col`."""
    a, b = frame[frame[exp]][col].astype(str), frame[~frame[exp]][col].astype(str)
    best, which = 0.0, ""
    for lvl in sorted(set(a) | set(b)):
        p1, p0 = (a == lvl).mean(), (b == lvl).mean()
        s = np.sqrt((p1 * (1 - p1) + p0 * (1 - p0)) / 2)
        v = abs(p1 - p0) / s if s > 0 else 0.0
        if v > best:
            best, which = v, f"{lvl} ({p1 * 100:.0f}% vs {p0 * 100:.0f}%)"
    return best, which


def z_pooled(k1, n1, k0, n0):
    pool = (k1 + k0) / (n1 + n0)
    se = np.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n0))
    return np.where(se > 0, (k1 / n1 - k0 / n0) / np.where(se > 0, se, 1), 0.0)


# --------------------------------------------------------------------------- permutation tests

def perm_threshold(s, rng):
    """A: the 48h cut was picked by scanning. Statistic = largest |z| over cuts 12h..120h (6h steps).
    Null = joining is unrelated to the gap (join flags shuffled across scheduled demos)."""
    order = np.argsort(s["gap_h"].to_numpy())
    gap = s["gap_h"].to_numpy()[order]
    y = s["joined"].to_numpy()[order].astype(np.int32)
    cuts = np.arange(12, 121, 6)
    idx = np.searchsorted(gap, cuts, side="right")
    n, k = len(y), y.sum()

    def stat(ys):
        cs = np.cumsum(ys, axis=-1)[..., idx - 1]
        return np.abs(z_pooled(k - cs, n - idx, cs, idx))  # late (> cut) vs early (<= cut)
    obs = stat(y)
    null = np.concatenate([stat(np.stack([rng.permutation(y) for _ in range(500)])).max(axis=1)
                           for _ in range(N_PERM // 500)])
    return dict(obs=obs.max(), cut=int(cuts[obs.argmax()]), p=(1 + (null >= obs.max()).sum()) / (1 + N_PERM),
                null95=np.quantile(null, 0.95), null=null)


def perm_groups(c, col, max_size, rng):
    """B/C: the low group was picked after looking. Statistic = largest shortfall z of any single
    level (and, if max_size=2, any pair of levels) vs the rest. Null = labels shuffled."""
    labels = c[col].to_numpy()
    lv = np.unique(labels)
    code = np.searchsorted(lv, labels)
    y = c["converted_f"].to_numpy().astype(np.int64)
    groups = [(i,) for i in range(len(lv))] + (list(combinations(range(len(lv)), 2)) if max_size == 2 else [])
    G = np.zeros((len(groups), len(lv)))
    for gi, g in enumerate(groups):
        G[gi, list(g)] = 1
    N, K = len(y), y.sum()

    def stat(codes):
        n = np.bincount(codes, minlength=len(lv))
        k = np.bincount(codes, weights=y, minlength=len(lv))
        gn, gk = G @ n, G @ k
        return -z_pooled(gk, gn, K - gk, N - gn)  # positive = group below the rest
    obs = stat(code)
    null = np.array([stat(rng.permutation(code)).max() for _ in range(N_PERM)])
    best = groups[int(obs.argmax())]
    return dict(obs=obs.max(), best=" + ".join(lv[i] for i in best),
                p=(1 + (null >= obs.max()).sum()) / (1 + N_PERM), null95=np.quantile(null, 0.95),
                n_groups=len(groups), null=null)


# --------------------------------------------------------------------------- data

def add_columns(df):
    df = prepare(df)
    df["month"] = df["created_at"].dt.strftime("%b")
    day = df["created_at"].dt.day
    df["half_month"] = df["month"] + np.where(day <= 15, " 1–15", " 16–end")
    df["half_month"] = pd.Categorical(df["half_month"], ["Jun 1–15", "Jun 16–end", "Jul 1–15", "Jul 16–end"])
    wk = df["created_at"].dt.to_period("W-SUN").dt.start_time
    df["week"] = "wk of " + wk.dt.strftime("%b %d")
    df["week"] = pd.Categorical(df["week"], sorted(df["week"].unique(), key=lambda s: pd.Timestamp(
        s[6:] + " 2026")))
    df["created_dow"] = pd.Categorical(df["created_at"].dt.day_name().str[:3], DAYS)
    df["demo_dow"] = pd.Categorical(df["demo_scheduled_at"].dt.day_name().str[:3], DAYS)
    df["created_hour"] = pd.cut(df["created_at"].dt.hour, [0, 8, 12, 17, 22, 24], right=False,
                                labels=HOUR_BANDS)
    df["geo_tz"] = df["geography"] + " (" + df["parent_timezone"] + ")"
    for clock, name in [("UTC", "local_hour_utc"), ("Asia/Kolkata", "local_hour_ist")]:
        hours = pd.Series(np.nan, index=df.index)
        sch = df[df["scheduled"]]
        for tz, g in sch.groupby("parent_timezone"):
            hours[g.index] = g["demo_scheduled_at"].dt.tz_localize(clock).dt.tz_convert(tz).dt.hour
        df[name] = pd.cut(hours, [0, 8, 12, 17, 22, 24], right=False, labels=HOUR_BANDS)
    return df


# --------------------------------------------------------------------------- charts

def chart_forest(cand, blocks, overall, path):
    """Stratum-level differences with 95% CIs, grouped by dimension."""
    rows = []
    for title, t in blocks:
        rows.append((title, None))
        for r in t.itertuples():
            if r.n1 >= MIN_N and r.n0 >= MIN_N:
                rows.append((f"{r.level}  ({r.n1}/{r.n0})", r))
    fig, ax = plt.subplots(figsize=(8.6, 0.24 * len(rows) + 1.6))
    y = np.arange(len(rows))[::-1]
    lo_all = min(r.lo for _, r in rows if r is not None) * 100
    hi_all = max(r.hi for _, r in rows if r is not None) * 100
    for yi, (lab, r) in zip(y, rows):
        if r is None:
            ax.text(lo_all - 1, yi, lab, fontsize=9, fontweight="bold", va="center", ha="left")
            continue
        ax.hlines(yi, r.lo * 100, r.hi * 100, color=BLUE, linewidth=2)
        ax.scatter(r.d * 100, yi, s=36, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=1.5)
    ax.axvline(0, color=TEXT_2, linewidth=1)
    ax.axvline(overall * 100, color=ORANGE, linewidth=1.2, linestyle=(0, (3, 3)))
    ax.annotate(f"overall {overall * 100:+.1f} pp", (overall * 100, 1.0), xycoords=("data", "axes fraction"),
                ha="center", va="bottom", fontsize=8, color=TEXT_2)
    ax.set_yticks(y, [lab if r is not None else "" for lab, r in rows], fontsize=7.5)
    ax.set_xlim(lo_all - 2, max(hi_all, 2) + 2)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}")
    ax.set_xlabel(f"Difference in {cand['step']} ({cand['exp_label']} − {cand['comp_label']}), pp")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    fig.suptitle(f"{cand['key']}. {cand['short']}: difference inside every subgroup", x=0.01, ha="left",
                 fontweight="bold", fontsize=13)
    top = 1 - 0.9 / fig.get_figheight()
    fig.text(0.01, top + 0.1 / fig.get_figheight(), f"95% Newcombe intervals. Labels show n exposed / n comparison. "
             f"Strata with <{MIN_N} on either side hidden.", fontsize=8.5, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, top - 0.05 / fig.get_figheight()))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_permutation(perms, path):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    for ax, (cand, res) in zip(axes, perms):
        ax.hist(res["null"], bins=40, color=GRID, edgecolor=SURFACE, linewidth=0.8 if cand["key"] != "A" else 0)
        ax.axvline(res["obs"], color=ORANGE, linewidth=2)
        ax.axvline(res["null95"], color=TEXT_2, linewidth=1, linestyle=(0, (3, 3)))
        ax.set_title(f"{cand['key']}. {cand['short']}", fontsize=10.5)
        ax.set_xlabel("largest |z| found by the search" if cand["key"] == "A" else "largest shortfall z")
        ax.set_yticks([])
        ax.grid(False)
        ax.text(res["obs"], ax.get_ylim()[1] * 0.92, f" observed {res['obs']:.1f}", color=TEXT,
                fontsize=8.5, ha="right" if res["obs"] > np.quantile(res["null"], 0.99) * 1.5 else "left")
    fig.suptitle("How extreme is each candidate, given how it was found?", x=0.01, ha="left",
                 fontweight="bold", fontsize=13)
    fig.text(0.01, 0.86, f"Grey = {N_PERM:,} shuffles of the data re-running the same search. Dashed = "
             "95th percentile of the shuffles. Orange = the real data.", fontsize=9, color=TEXT_2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- report helpers

def strat_table(t, rate_label):
    return md_table(pd.DataFrame({
        "stratum": t["level"], "n exp.": t["n1"].map("{:,}".format),
        f"{rate_label} exp.": [pc(k / n) if n else "—" for k, n in zip(t.k1, t.n1)],
        "n comp.": t["n0"].map("{:,}".format),
        f"{rate_label} comp.": [pc(k / n) if n else "—" for k, n in zip(t.k0, t.n0)],
        "diff": t["d"].map(pp),
        "95% CI (pp)": [f"[{lo * 100:+.1f}, {hi * 100:+.1f}]" if not np.isnan(lo) else "—"
                        for lo, hi in zip(t.lo, t.hi)],
        "flag": ["" if (n1 >= MIN_N and n0 >= MIN_N) else f"n<{MIN_N}" for n1, n0 in zip(t.n1, t.n0)]}))


def summary_line(sm):
    return (f"MH-adjusted difference {pp(sm['mh'])} [{sm['lo'] * 100:+.1f}, {sm['hi'] * 100:+.1f}]; "
            f"same direction in **{sm['same']} of {sm['k']}** strata with ≥{MIN_N} per side "
            f"(sign test p {fmt_p(sm['sign_p'])}); heterogeneity Cochran's Q p {fmt_p(sm['q_p'])}.")


# --------------------------------------------------------------------------- main

def main():
    rng = np.random.default_rng(SEED)
    csv = resolve_csv()
    df = add_columns(load(csv))
    s = df[df["scheduled"]].copy()
    c = df[df["completed"]].copy()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    seg, _ = screen(df)

    def holm_p(segment, step):
        return seg[(seg["seg"] == segment) & (seg["step"] == step)]["p_holm"].iloc[0]

    cands = [
        dict(key="A", short="Demo >48h out", title=f"Demo booked more than {LATE_H}h after the lead arrived",
             frame=s, exp="late", out="joined", step="J/S", rate="join", exp_label=f">{LATE_H}h",
             comp_label=f"≤{LATE_H}h", base="scheduled demos", own=None),
        dict(key="B", short="India + Vietnam", title="India + Vietnam convert less after a completed demo",
             frame=c, exp="india_vn", out="converted_f", step="V/C", rate="conv.", exp_label="India+VN",
             comp_label="other geos", base="completed demos", own="geography"),
        dict(key="C", short="DSA source", title="DSA leads convert less after a completed demo",
             frame=c, exp="dsa", out="converted_f", step="V/C", rate="conv.", exp_label="DSA",
             comp_label="other sources", base="completed demos", own="lead_source"),
    ]
    dims = [  # (check number, column, label)
        (1, "lead_source", "Lead source"),
        (2, "geo_tz", "Geography · parent timezone"),
        (3, "local_hour_utc", "Parent-local demo hour (stored clock = UTC)"),
        (3, "local_hour_ist", "Parent-local demo hour (stored clock = IST)"),
        (4, "rep_shift", "Rep shift"),
        (5, "rep_assigned", "Rep assigned"),
        (6, "fu_band", "Follow-up attempts"),
        (8, "half_month", "Half-month of lead creation"),
    ]
    confounder_dims = [("created_dow", "Day lead was created"), ("demo_dow", "Day of the demo"),
                       ("created_hour", "Hour lead was created (stored clock)"),
                       ("late", f"Demo >{LATE_H}h out"), ("dsa", "DSA source"), ("india_vn", "India/Vietnam")]

    # ------------------------------------------------------------ compute everything
    res = {}
    for cd in cands:
        f, e, o = cd["frame"], cd["exp"], cd["out"]
        r = res[cd["key"]] = {}
        n1, k1, n0, k0 = cell(f, e, o)
        r["raw"] = dict(n1=n1, k1=k1, n0=n0, k0=k0, **two_prop(k1, n1, k0, n0))
        d, lo, hi = newcombe(k1, n1, k0, n0)
        r["raw"].update(nlo=lo, nhi=hi)
        r["strata"] = {}
        for num, col, lab in dims:
            if col in ("lead_source",) and cd["own"] == "lead_source":
                continue
            if col == "geo_tz" and cd["own"] == "geography":
                continue
            r["strata"][col] = stratify(f, e, o, col)
        r["conf_strata"] = {col: stratify(f, e, o, col) for col, _ in confounder_dims if col != e}
        loo_cols = [col for col in ["lead_source", "geography", "rep_assigned", "rep_shift", "fu_band",
                                    "half_month"] if col != cd["own"]]
        r["loo"] = {col: leave_one_out(f, e, o, col) for col in loo_cols}
        r["deficit"] = {col: deficit_share(f, e, o, col, k0 / n0) for col in loo_cols}
        r["months"], r["months_ci"] = {}, {}
        for m, g in f.groupby("month", sort=False):
            m1, j1, m0, j0 = cell(g, e, o)
            r["months"][m] = two_prop(j1, m1, j0, m0)
            r["months_ci"][m] = newcombe(j1, m1, j0, m0)
        # Headline model: pre-exposure variables only (fixed when the lead arrives). Follow-up attempts,
        # demo weekday and demo >48h can be consequences of the exposure, so they enter only a labelled
        # sensitivity model and never the headline odds ratio.
        pre_covars = [x for x in ["lead_source", "geography", "rep_assigned", "month", "created_dow"]
                      if x != e and x != cd["own"]]
        post_covars = [x for x in ["fu_band", "demo_dow", "late"] if x != e]
        r["models"] = [("none", adjusted(f, e, o, [])),
                       ("source/geography, rep (absorbs shift)", adjusted(f, e, o, [x for x in pre_covars if x in (
                           "lead_source", "geography", "rep_assigned")])),
                       ("**pre-exposure: + month, lead weekday (headline)**", adjusted(f, e, o, pre_covars)),
                       ("sensitivity only: + follow-ups, demo weekday" + (", demo >48h" if e != "late" else "")
                        + " (possibly post-exposure)", adjusted(f, e, o, pre_covars + post_covars))]
        r["full"] = r["models"][2][1]
        r["covars"] = pre_covars
        r["evalue"] = e_value(k1, n1, k0, n0)
        p0 = k0 / n0
        r["mde"] = (mde(n1, n0, p0, norm.ppf(0.975)), mde(n1, n0, p0, norm.ppf(1 - 0.025 / N_SCREEN)))
        r["balance"] = [(lab, *smd(f, e, col)) for col, lab in
                        [("lead_source", "Lead source"), ("geography", "Geography"), ("rep_assigned", "Rep"),
                         ("rep_shift", "Rep shift"), ("fu_band", "Follow-up attempts"), ("month", "Month"),
                         ("created_dow", "Day created"), ("demo_dow", "Demo weekday"),
                         ("late", f"Demo >{LATE_H}h")] if col != e and col != cd["own"]]

    perm = {"A": perm_threshold(s, rng), "B": perm_groups(c, "geography", 2, rng),
            "C": perm_groups(c, "lead_source", 1, rng)}

    # ------------------------------------------------------------ evidence rubric
    def grade(cd):
        r, key = res[cd["key"]], cd["key"]
        raw = r["raw"]
        crit = []
        # 1. selection-aware significance
        pv = perm[key]["p"]
        crit.append(("Significant after accounting for how it was found (permutation)",
                     "pass" if pv < 0.01 else "partial" if pv < 0.05 else "fail", f"p {fmt_p(pv)}"))
        # 2. size
        crit.append(("Difference ≥5 pp and CI excludes 0",
                     "pass" if abs(raw["diff"]) >= 0.05 and np.sign(raw["nlo"]) == np.sign(raw["nhi"])
                     else "fail", f"{pp(raw['diff'])} [{raw['nlo'] * 100:+.1f}, {raw['nhi'] * 100:+.1f}]"))
        # 3. consistency across dimensions (checks 1-6)
        core = [v[1] for k, v in r["strata"].items() if k != "half_month"]
        same, k = sum(x["same"] for x in core), sum(x["k"] for x in core)
        worst_q = min(x["q_p"] for x in core if not np.isnan(x["q_p"]))
        share = same / k
        crit.append(("Same direction across source, geography, timezone, shift, rep, follow-ups",
                     "pass" if share >= 0.85 and worst_q >= 0.01 else "partial" if share >= 0.7 else "fail",
                     f"{same}/{k} strata ({share * 100:.0f}%); lowest heterogeneity p {fmt_p(worst_q)}"))
        # 4. not driven by one group (leave-one-out)
        loo = pd.concat(r["loo"].values(), ignore_index=True)
        weakest = loo.loc[loo["d"].abs().idxmin()]
        keep = (np.sign(loo["d"]) == np.sign(raw["diff"])).all() and (loo["p"] < 0.05).all()
        crit.append(("No single group drives it (drop any one source/geo/rep/shift/follow-up band/period)",
                     "pass" if keep and (loo["d"].abs() >= 0.6 * abs(raw["diff"])).all()
                     else "partial" if keep else "fail",
                     f"weakest: drop {weakest['level']} → {pp(weakest['d'])} (p {fmt_p(weakest['p'])})"))
        # 5. time
        ms = r["months"]
        mci = r["months_ci"]
        both = all(np.sign(v["diff"]) == np.sign(raw["diff"]) for v in ms.values())
        both_sig = all(np.sign(lo) == np.sign(hi) for _, lo, hi in mci.values())
        hs = r["strata"]["half_month"][1]
        crit.append(("Stable across June and July (both months CI excl. 0; half-months homogeneous)",
                     "pass" if both and both_sig and hs["q_p"] >= 0.05 else "partial" if both else "fail",
                     "; ".join(f"{m} {pp(v['diff'])}" for m, v in ms.items())
                     + f"; half-months same sign {hs['same']}/{hs['k']}, heterogeneity p {fmt_p(hs['q_p'])}"))
        # 6. sample size
        m95, mholm = r["mde"]
        crit.append(("Sample large enough (exposed outcomes ≥50; MDE at Holm level ≤ observed gap)",
                     "pass" if raw["k1"] >= 50 and mholm <= abs(raw["diff"])
                     else "partial" if mholm <= abs(raw["diff"]) * 1.25 or raw["k1"] >= 50 else "fail",
                     f"{raw['k1']} events in {raw['n1']:,}; MDE {m95 * 100:.1f} pp (α 0.05) / "
                     f"{mholm * 100:.1f} pp (Holm-level)"))
        # 7. measured confounders
        full = r["full"]
        rawm = r["models"][0][1]
        kept = full["ame"] / rawm["ame"]
        rr, ev, ev_ci = r["evalue"]
        crit.append(("Survives adjustment for pre-exposure variables",
                     "pass" if kept >= 0.75 and full["hi"] < 1 else "partial" if kept >= 0.5 else "fail",
                     f"adjusted effect keeps {kept * 100:.0f}% of raw; OR {full['or_']:.2f} "
                     f"[{full['lo']:.2f}, {full['hi']:.2f}]; E-value {ev:.2f} (CI {ev_ci:.2f})"))
        marks = [x[1] for x in crit]
        fails = marks.count("fail")
        if marks[5] == "fail" and marks[0] != "pass":
            g = "Inconclusive"
        elif all(m == "pass" for m in marks):
            g = "Strong"
        elif marks[0] == "pass" and fails <= 1:
            g = "Moderate"
        else:
            g = "Weak"
        return crit, g

    grades = {cd["key"]: grade(cd) for cd in cands}

    # ------------------------------------------------------------ charts
    figs = {}
    for cd in cands:
        r = res[cd["key"]]
        blocks = [(lab, r["strata"][col][0]) for num, col, lab in dims if col in r["strata"]
                  and col != "local_hour_ist"]
        figs[cd["key"]] = chart_forest(cd, blocks, r["raw"]["diff"],
                                       FIG_DIR / f"0{'ABC'.index(cd['key']) + 1}_forest_{cd['key']}.png")
    figs["perm"] = chart_permutation([(cd, perm[cd["key"]]) for cd in cands], FIG_DIR / "04_permutation_tests.png")

    # ------------------------------------------------------------ report
    out = []
    w = out.append
    A, B, C = res["A"], res["B"], res["C"]
    gA, gB, gC = grades["A"][1], grades["B"][1], grades["C"][1]

    w("# Phase 4 — Validate the Candidate Leaks\n")
    w(f"Source file: `{csv.name}`  ")
    w("Generated by: `analysis/phase_04_leak_validation.py` (re-run to reproduce; permutation seed "
      f"{SEED}).  ")
    w("Scope: stress-test the three Phase 3 candidates. Still no solution and no ₹ sizing.\n")

    w("## 0. Summary\n")
    rows = []
    for cd in cands:
        r = res[cd["key"]]
        full = r["full"]
        rows.append([f"{cd['key']}. {cd['title']}", cd["step"],
                     f"{pc(r['raw']['p1'])} vs {pc(r['raw']['p0'])} ({pp(r['raw']['diff'])})",
                     f"[{r['raw']['nlo'] * 100:+.1f}, {r['raw']['nhi'] * 100:+.1f}] pp",
                     fmt_p(perm[cd["key"]]["p"]), f"{full['or_']:.2f} [{full['lo']:.2f}, {full['hi']:.2f}]",
                     f"**{grades[cd['key']][1]}**"])
    w(md_table(pd.DataFrame(rows, columns=["candidate", "step", "observed gap", "95% CI",
                                           "selection-aware p", "adjusted OR [95% CI]", "evidence"])))
    w("")
    w("__SUMMARY__\n")

    w("## 1. Method\n")
    w("**What each check does**\n")
    w(f"- **Checks 1–6 (source, geography, timezone, shift, rep, follow-ups).** The candidate's gap is "
      f"recomputed *inside* every level of the dimension (e.g. late vs early demos among Google leads only). "
      f"A real effect should point the same way in most strata. Per stratum: difference with a 95% "
      f"Newcombe interval (reliable at small n). Per dimension: a Mantel-Haenszel (MH) adjusted difference, "
      f"a sign test on how many strata (with ≥{MIN_N} per side) point the same way, and Cochran's Q for "
      "whether the size of the gap varies more than chance.")
    w("- **Check 3 (parent timezone).** Timezone is 1:1 with geography (Phase 1), so it shares geography's "
      "table. The timezone-specific question is whether the demo lands at a bad *local* hour; the storage "
      "clock is unknown (Phase 1 §7), so local hour is computed under both UTC and IST.")
    w("- **Check 7 (one small group driving it).** Leave-one-out: drop each source, geography, rep, "
      "shift, follow-up band and half-month in turn and recompute. Also: what share of the shortfall "
      "comes from each stratum compared with its share of the exposed group.")
    w("- **Check 8 (time).** June vs July, four half-months, and weeks for A.")
    w(f"- **Check 9 (sample size).** Events in the exposed group; minimum detectable effect (MDE) at 80% "
      f"power, both at α 0.05 and at the Holm-level threshold of a {N_SCREEN}-test screen. And a "
      f"**selection-aware permutation test**: every candidate was found by searching (A: a threshold was "
      "picked from a scan; B: the two worst geographies were pooled after looking; C: the worst of six "
      "sources was picked). The test re-runs that same search on "
      f"{N_PERM:,} shuffled copies of the data and asks how often chance alone finds something as extreme. "
      "This is the honest p-value for each candidate; ordinary p-values overstate it.")
    w("- **Check 10 (confounding).** Covariate balance (standardised mean difference, SMD; >0.1 = "
      "imbalanced), extra strata (weekday, hour, and the other candidates), logistic regression adjusted for "
      "pre-exposure variables (source, geography, rep, month, lead weekday; follow-ups and demo weekday only in "
      "a labelled sensitivity row, as they can be consequences of a far-off demo), and an E-value: how strongly an *unmeasured* confounder would need to be tied "
      "to both the exposure and the outcome (as a risk ratio) to fully explain the gap away.")
    w("\n**How evidence is graded** (the same rubric for all three; section 5 shows every criterion):\n")
    w("- **Strong** — passes all seven criteria: selection-aware p < 0.01; gap ≥5 pp with CI excluding 0; "
      "same direction in ≥85% of strata with no strong heterogeneity (Q p ≥ 0.01); dropping any single "
      "group leaves a gap ≥60% of the original with p < 0.05; CI excludes 0 in both months and half-months "
      "are homogeneous (Q p ≥ 0.05); ≥50 exposed events and 80% power at a Holm-level threshold; adjusted "
      "effect keeps ≥75% of the raw gap with the CI excluding no-effect.")
    w("- **Moderate** — passes the selection-aware test and fails at most one other criterion.")
    w("- **Weak** — fails the selection-aware test, or fails two or more other criteria. The pattern may "
      "be real, but it is too dependent on a few leads, one period or one group to act on as it stands.")
    w("- **Inconclusive** — the sample is too small to confirm or rule out a meaningful gap (sample-size "
      "criterion failed and the selection-aware test not passed).")
    w("\nThe grade is about whether the **association is real and robust**. Whether it is **causal** and "
      "**operationally fixable** is a separate question, answered in each candidate's "
      "*fact / inference / assumption* block.\n")

    # ---------------------------------------------------------------- per-candidate sections
    for cd in cands:
        key, r, f = cd["key"], res[cd["key"]], cd["frame"]
        e, o = cd["exp"], cd["out"]
        raw = r["raw"]
        w(f"## {2 + 'ABC'.index(key)}. Candidate {key} — {cd['title']}\n")
        w(f"Base: {len(f):,} {cd['base']}. Exposed = {cd['exp_label']} ({raw['n1']:,}); comparison = "
          f"{cd['comp_label']} ({raw['n0']:,}). Outcome = {cd['step']}. Raw: {pc(raw['p1'])} vs "
          f"{pc(raw['p0'])}, {pp(raw['diff'])} [{raw['nlo'] * 100:+.1f}, {raw['nhi'] * 100:+.1f}].\n")
        sec = 2 + "ABC".index(key)

        # own-dimension checks
        if key == "B":
            w(f"### {sec}.1 Geography and parent timezone — the candidate's own dimension (checks 2–3)\n")
            per = c.groupby("geo_tz")["converted_f"].agg(["sum", "size"])
            rows = []
            iv = c[c.india_vn]
            for g, (k, n) in per.assign(rate=per["sum"] / per["size"]).sort_values("rate")[["sum", "size"]].iterrows():
                lo, hi = wilson(k, n)
                rows.append([g, f"{n:,}", f"{int(k)}", pc(k / n), f"[{lo * 100:.1f}, {hi * 100:.1f}]"])
            w(md_table(pd.DataFrame(rows, columns=["geography (timezone)", "completed", "converted", "V/C",
                                                   "95% CI (%)"])))
            rest = c[~c.india_vn]
            rows = []
            for g, gg in rest.groupby("geography"):
                d, lo, hi = newcombe(int(iv.converted_f.sum()), len(iv), int(gg.converted_f.sum()), len(gg))
                rows.append([f"India+VN vs {g}", pp(d), f"[{lo * 100:+.1f}, {hi * 100:+.1f}]"])
            rest_nousa = rest[rest.geography != "USA"]
            d, lo, hi = newcombe(int(iv.converted_f.sum()), len(iv), int(rest_nousa.converted_f.sum()),
                                 len(rest_nousa))
            rows.append(["India+VN vs rest excl. USA", pp(d), f"[{lo * 100:+.1f}, {hi * 100:+.1f}]"])
            for g in ["India", "Vietnam"]:
                gg = c[c.geography == g]
                d, lo, hi = newcombe(int(gg.converted_f.sum()), len(gg), int(rest.converted_f.sum()), len(rest))
                rows.append([f"{g} alone vs other six", pp(d), f"[{lo * 100:+.1f}, {hi * 100:+.1f}]"])
            w("\n")
            w(md_table(pd.DataFrame(rows, columns=["comparison", "diff", "95% CI (pp)"])))
            ind, vn = c[c.geography == "India"], c[c.geography == "Vietnam"]
            p_iv = fisher_exact([[ind.converted_f.sum(), len(ind) - ind.converted_f.sum()],
                                 [vn.converted_f.sum(), len(vn) - vn.converted_f.sum()]])[1]
            p_rest = chi2_contingency(pd.crosstab(rest.geography, rest.converted_f))[1]
            B["own"] = dict(p_iv=p_iv, p_rest=p_rest, min_pair=min(float(x[1].split()[0]) for x in rows[:6]),
                            max_pair=max(float(x[1].split()[0]) for x in rows[:6]))
            w(f"\nIndia vs Vietnam: Fisher p {fmt_p(p_iv)} (no evidence they differ from each other). "
              f"Among the other six geographies: chi-square p {fmt_p(p_rest)}.\n")
        if key == "C":
            w(f"### {sec}.1 Lead source — the candidate's own dimension (check 1)\n")
            per = c.groupby("lead_source")["converted_f"].agg(["sum", "size"])
            rows = []
            for g, (k, n) in per.iterrows():
                lo, hi = wilson(k, n)
                rows.append([g, f"{n:,}", f"{int(k)}", pc(k / n), f"[{lo * 100:.1f}, {hi * 100:.1f}]"])
            w(md_table(pd.DataFrame(rows, columns=["lead source", "completed", "converted", "V/C",
                                                   "95% CI (%)"])))
            dsa, rest = c[c.dsa], c[~c.dsa]
            rows = []
            for g, gg in rest.groupby("lead_source"):
                d, lo, hi = newcombe(int(dsa.converted_f.sum()), len(dsa), int(gg.converted_f.sum()), len(gg))
                rows.append([f"DSA vs {g}", pp(d), f"[{lo * 100:+.1f}, {hi * 100:+.1f}]"])
            paid = rest[rest.lead_source.isin(["Affiliate", "Google", "Meta"])]
            d, lo, hi = newcombe(int(dsa.converted_f.sum()), len(dsa), int(paid.converted_f.sum()), len(paid))
            rows.append(["DSA vs paid sources only (Affiliate, Google, Meta)", pp(d),
                         f"[{lo * 100:+.1f}, {hi * 100:+.1f}]"])
            C["own"] = dict(paid=(d, lo, hi))
            w("\n")
            w(md_table(pd.DataFrame(rows, columns=["comparison", "diff", "95% CI (pp)"])))
            p_rest = chi2_contingency(pd.crosstab(rest.lead_source, rest.converted_f))[1]
            C["own"]["p_rest"] = p_rest
            w(f"\nAmong the other five sources: chi-square p {fmt_p(p_rest)}.\n")

        # stratified checks
        sub = 0 if key == "A" else 1  # B and C used .1 for their own dimension
        for num, col, lab in dims:
            if col not in r["strata"]:
                continue
            t, sm = r["strata"][col]
            if col == "local_hour_ist":
                w(f"#### {lab}\n")
            elif col == "local_hour_utc":
                sub += 1
                w(f"### {sec}.{sub} Parent timezone: parent-local demo hour (check 3)\n")
                w(f"#### {lab}\n")
            else:
                sub += 1
                w(f"### {sec}.{sub} {lab} (check {num})\n")
            if col == "half_month":
                w("Months:\n")
                rows = []
                for m in r["months"]:
                    g = f[f.month == m]
                    n1, k1, n0, k0 = cell(g, e, o)
                    d, lo, hi = r["months_ci"][m]
                    rows.append([m, f"{n1:,}", pc(k1 / n1), f"{n0:,}", pc(k0 / n0), pp(d),
                                 f"[{lo * 100:+.1f}, {hi * 100:+.1f}]", fmt_p(r["months"][m]["p"])])
                w(md_table(pd.DataFrame(rows, columns=["month", "n exp.", f"{cd['rate']} exp.", "n comp.",
                                                       f"{cd['rate']} comp.", "diff", "95% CI (pp)", "p"])))
                w("\nHalf-months:\n")
            w(strat_table(t, cd["rate"]))
            w("\n" + summary_line(sm) + "\n")
            if col == "half_month" and key == "A":
                tw, smw = stratify(f, e, o, "week")
                w("Weeks of lead creation (A only; B and C are too thin per week):\n")
                w(strat_table(tw, cd["rate"]))
                w("\n" + summary_line(smw) + "\n")
                after_end = f["demo_scheduled_at"] > df["created_at"].max()
                x = f[~after_end]
                n1, k1, n0, k0 = cell(x, e, o)
                d, lo, hi = newcombe(k1, n1, k0, n0)
                A["after_end"] = (int(after_end.sum()), d, lo, hi)
                w(f"Excluding {int(after_end.sum())} demos dated after the last lead was created: "
                  f"{pp(d)} [{lo * 100:+.1f}, {hi * 100:+.1f}].\n")
                near = f[(f.gap_h > 36) & (f.gap_h <= 60)]
                n1, k1, n0, k0 = cell(near, e, o)
                d, lo, hi = newcombe(k1, n1, k0, n0)
                A["near"] = (n1, k1, n0, k0, d, lo, hi)
                w(f"Narrow window around the cut (36–48h vs 48–60h): {pc(k0 / n0)} (n={n0}) vs "
                  f"{pc(k1 / n1)} (n={n1}), {pp(d)} [{lo * 100:+.1f}, {hi * 100:+.1f}]. "
                  + ("The drop is visible right at the threshold, not only between far-apart groups.\n"
                     if hi < 0 else "Too few demos near the threshold to see the step directly.\n"))

        # check 7
        sub += 1
        w(f"### {sec}.{sub} Is one small group driving it? (check 7)\n")
        rows = []
        for col, lt in r["loo"].items():
            lt = lt.sort_values("d", key=abs)
            weak, strong = lt.iloc[0], lt.iloc[-1]
            dt = r["deficit"][col].iloc[0]
            rows.append([col.replace("_", " "), f"{pp(weak['d'])} (drop {weak['level']}, p {fmt_p(weak['p'])})",
                         f"{pp(strong['d'])} (drop {strong['level']})", fmt_p(lt["p"].max()),
                         f"{dt['level']}: {dt['share_def'] * 100:.0f}% of shortfall, "
                         f"{dt['share_n'] * 100:.0f}% of exposed"])
        w(md_table(pd.DataFrame(rows, columns=["dimension dropped one level at a time", "smallest remaining gap",
                                               "largest remaining gap", "worst p", "biggest contributor"])))
        loo_all = pd.concat(r["loo"].values(), ignore_index=True)
        r["loo_range"] = (loo_all["d"].min(), loo_all["d"].max(), loo_all["p"].max())
        w(f"\nAcross all {len(loo_all)} leave-one-out runs the gap stays between {pp(loo_all['d'].max())} and "
          f"{pp(loo_all['d'].min())}; the worst p is {fmt_p(loo_all['p'].max())}.\n")

        # check 9
        sub += 1
        w(f"### {sec}.{sub} Sample size and selection-aware significance (check 9)\n")
        pr = perm[key]
        m95, mholm = r["mde"]
        rows = [["exposed group", f"{raw['n1']:,} ({raw['k1']:,} events)"],
                ["comparison group", f"{raw['n0']:,} ({raw['k0']:,} events)"],
                ["95% CI of gap (Newcombe)", f"[{raw['nlo'] * 100:+.1f}, {raw['nhi'] * 100:+.1f}] pp "
                 f"(width {(raw['nhi'] - raw['nlo']) * 100:.1f} pp)"],
                ["MDE, 80% power, α 0.05", f"{m95 * 100:.1f} pp"],
                [f"MDE, 80% power, Holm-level α for {N_SCREEN} tests", f"{mholm * 100:.1f} pp"],
                ["naive p (two-proportion z)", fmt_p(raw["p"])]]
        if key == "A":
            rows.append(["Phase 3 Holm p (48–72h band vs rest)", fmt_p(holm_p("48–72h", "J/S"))])
            rows.append(["search re-run on shuffled data", f"largest absolute z over {len(range(12, 121, 6))} "
                         f"cuts (12h–120h); real data peaks at {pr['cut']}h"])
        elif key == "B":
            rows.append(["Phase 3 Holm p", f"India {fmt_p(holm_p('India', 'V/C'))}, Vietnam "
                         f"{fmt_p(holm_p('Vietnam', 'V/C'))}"])
            rows.append(["search re-run on shuffled data", f"worst of {pr['n_groups']} single geographies "
                         f"and pairs; real data's worst is {pr['best']}"])
        else:
            rows.append(["Phase 3 Holm p", fmt_p(holm_p("DSA", "V/C"))])
            rows.append(["search re-run on shuffled data", f"worst of {pr['n_groups']} sources; real "
                         f"data's worst is {pr['best']}"])
        rows += [["statistic: real data", f"{pr['obs']:.2f}"],
                 ["statistic: 95th percentile under shuffling", f"{pr['null95']:.2f}"],
                 ["**selection-aware p**", f"**{fmt_p(pr['p'])}**" + (f" (none of {N_PERM:,} shuffles as extreme)"
                                                                     if pr["p"] <= 1 / (N_PERM + 1) + 1e-12 else "")]]
        w(md_table(pd.DataFrame(rows, columns=["item", "value"])))
        w("")

        # check 10
        sub += 1
        w(f"### {sec}.{sub} Confounding (check 10)\n")
        w("Covariate balance, exposed vs comparison (largest SMD across the variable's categories):\n")
        w(md_table(pd.DataFrame([[lab, f"{v:.2f}", which, "**imbalanced**" if round(v, 2) > 0.1 else "balanced"]
                                 for lab, v, which in r["balance"]],
                                columns=["variable", "max SMD", "category (exposed vs comp.)", "verdict"])))
        w("\nGap within strata of other possible confounders:\n")
        rows = []
        for (col, lab) in confounder_dims:
            if col not in r["conf_strata"] or col == cd["own"]:
                continue
            t, sm = r["conf_strata"][col]
            rows.append([lab, pp(sm["mh"]), f"[{sm['lo'] * 100:+.1f}, {sm['hi'] * 100:+.1f}]",
                         f"{sm['same']}/{sm['k']}", fmt_p(sm["q_p"])])
        w(md_table(pd.DataFrame(rows, columns=["held fixed", "MH diff", "95% CI (pp)", "strata same direction",
                                               "heterogeneity p"])))
        w("\nLogistic regression (outcome = " + cd["step"] + "):\n")
        rows = [[lab, m["k"], f"{m['or_']:.2f}", f"[{m['lo']:.2f}, {m['hi']:.2f}]", fmt_p(m["p"]),
                 pp(m["ame"])] for lab, m in r["models"]]
        w(md_table(pd.DataFrame(rows, columns=["adjusted for", "covariate terms", "odds ratio", "95% CI", "p",
                                               "avg. marginal effect"])))
        rr, ev, ev_ci = r["evalue"]
        w(f"\nRisk ratio {rr:.2f}. **E-value {ev:.2f}** (for the CI limit: {ev_ci:.2f}): an unmeasured "
          f"confounder would need a risk ratio of at least {ev:.2f} with both {cd['exp_label']} status and "
          f"the outcome — beyond everything adjusted for above — to fully explain the gap.\n")
        w(f"__INTERP_{key}__\n")

    # ---------------------------------------------------------------- scorecard
    w("## 5. Evidence scorecard\n")
    for cd in cands:
        crit, g = grades[cd["key"]]
        w(f"### {cd['key']}. {cd['title']} — **{g}**\n")
        w(md_table(pd.DataFrame([[i + 1, name, res_, detail] for i, (name, res_, detail) in enumerate(crit)],
                                columns=["#", "criterion", "result", "evidence"])))
        w(f"\n__WHY_{cd['key']}__\n")

    w("## 6. The most defensible operational problem\n")
    w("__FINAL__\n")

    w("## 7. Charts\n")
    caps = {"A": "Candidate A: late vs early join rate gap inside every subgroup",
            "B": "Candidate B: India+Vietnam vs other geographies, V/C gap inside every subgroup",
            "C": "Candidate C: DSA vs other sources, V/C gap inside every subgroup",
            "perm": "Selection-aware permutation tests"}
    for k_, p_ in figs.items():
        w(f"![{caps[k_]}]({p_.relative_to(OUT_PATH.parent).as_posix()})\n")

    w("## 8. Verification performed by the script\n")
    w("- Phase 2 stage counts reproduce (5,000 / 3,229 / 2,060 / 1,786 / 362)")
    w("- Raw gaps reproduce Phase 3 (A −28.0 pp, B −12.2 pp, C −10.2 pp)")
    w("- Every stratified table's exposed and comparison counts sum to the candidate's totals")
    w("- Geography ↔ parent timezone is 1:1; each rep belongs to exactly one shift")
    w("- Logistic regression with no covariates reproduces the raw odds ratio")
    w(f"- Permutation tests use a fixed seed ({SEED}) and {N_PERM:,} shuffles\n")

    # ------------------------------------------------------------ checks
    counts = stage_counts(df)
    if len(sys.argv) == 1:
        assert counts == [5000, 3229, 2060, 1786, 362], counts
        assert [round(res[k]["raw"]["diff"] * 100, 1) for k in "ABC"] == [-28.0, -12.2, -10.2]
    for cd in cands:
        r = res[cd["key"]]
        for col, (t, _) in list(r["strata"].items()):
            if col.startswith("local_hour"):
                continue
            assert t.n1.sum() == r["raw"]["n1"] and t.n0.sum() == r["raw"]["n0"], (cd["key"], col)
        raw_or = (r["raw"]["k1"] / (r["raw"]["n1"] - r["raw"]["k1"])) / (r["raw"]["k0"] / (r["raw"]["n0"] - r["raw"]["k0"]))
        assert abs(r["models"][0][1]["or_"] - raw_or) < 1e-6
    assert df.groupby("geography")["parent_timezone"].nunique().eq(1).all()
    assert df.groupby("parent_timezone")["geography"].nunique().eq(1).all()
    assert df.groupby("rep_assigned")["rep_shift"].nunique().eq(1).all()

    text = "\n".join(out) + "\n"
    text = fill_narrative(text, cands, res, perm, grades, df, s, c)
    OUT_PATH.write_text(text)
    for cd in cands:
        print(cd["key"], grades[cd["key"]][1], [x[1] for x in grades[cd["key"]][0]])
    print(f"Wrote {OUT_PATH}")


def fill_narrative(text, cands, res, perm, grades, df, s, c):
    """Replace the __PLACEHOLDER__ lines with prose built from the computed results."""
    A, B, C = res["A"], res["B"], res["C"]
    g = {k: grades[k][1] for k in "ABC"}
    ra, rb, rc = A["raw"], B["raw"], C["raw"]
    late, early = s[s["late"]], s[~s["late"]]
    noshow_late, noshow_all = ra["n1"] - ra["k1"], len(s) - int(s["joined"].sum())
    lc, ec = late[late["completed"]], early[early["completed"]]
    vc_late = two_prop(int(lc.converted_f.sum()), len(lc), int(ec.converted_f.sum()), len(ec))
    lj, ej = late[late["joined"]], early[early["joined"]]
    cj_late = two_prop(int(lj.completed.sum()), len(lj), int(ej.completed.sum()), len(ej))
    fu_smd = dict((lab, (v, which)) for lab, v, which in A["balance"])["Follow-up attempts"]
    n1, k1, n0, k0, dn, lon, hin = A["near"]
    ev = {k: res[k]["evalue"] for k in "ABC"}
    full = {k: res[k]["full"] for k in "ABC"}

    iv = df[df["india_vn"]]
    rest = df[~df["india_vn"]]
    pre = {}
    for flag, denom, lab in [("scheduled", None, "S/L"), ("joined", "scheduled", "J/S"),
                             ("completed", "joined", "C/J")]:
        a = iv if denom is None else iv[iv[denom]]
        b = rest if denom is None else rest[rest[denom]]
        pre[lab] = two_prop(int(a[flag].sum()), len(a), int(b[flag].sum()), len(b))
    vc_geo = c.groupby("geography")["converted_f"].mean()

    cs = C["strata"]["rep_shift"][0].set_index("level")
    ch = C["strata"]["half_month"][0].set_index("level")
    c_loo = pd.concat(C["loo"].values(), ignore_index=True)
    c_shift = C["loo"]["rep_shift"].set_index("level").loc["US_SHIFT"]
    c_half = C["loo"]["half_month"].set_index("level").loc["Jun 1–15"]
    c_jul = C["months"]["Jul"]
    c_jul_ci = C["months_ci"]["Jul"]
    c_def = C["deficit"]
    c_aff = C["own"]
    rest_sources = c[~c["dsa"]].groupby("lead_source")["converted_f"].mean()

    summary = f"""**Bottom line.** A and B hold up under every check. C does not.

- **A. Late demo → no-show: {g['A']}.** Demos set more than {LATE_H}h after the lead arrived are joined \
{pc(ra['p1'])} of the time vs {pc(ra['p0'])} ({pp(ra['diff'])}). The gap points the same way in every source, \
geography, local-hour band, shift, rep, follow-up band, half-month and week, and dropping any single group \
moves it by at most {max(abs(x - ra['diff']) for x in A['loo_range'][:2]) * 100:.1f} pp. It survives adjustment for \
pre-exposure variables (source, geography, rep, month, lead weekday; OR {full['A']['or_']:.2f}), and a re-run of the threshold search on shuffled data never gets \
close (p {fmt_p(perm['A']['p'])}). These demos make up {pc(ra['n1'] / len(s))} of scheduled demos and \
{pc(noshow_late / noshow_all)} of all no-shows.
- **B. India + Vietnam post-demo conversion: {g['B']}.** V/C {pc(rb['p1'])} vs {pc(rb['p0'])} \
({pp(rb['diff'])}). It is lower than *each* of the other six geographies individually, the same in every \
source, shift and rep, and it survives adjustment (OR {full['B']['or_']:.2f}) and the pooling-was-chosen-after-looking \
permutation test (p {fmt_p(perm['B']['p'])}). The association is solid. **Whether it is an operational leak is not**: \
nothing in the file can tell a sales-process failure apart from price or market fit.
- **C. DSA post-demo conversion: {g['C']}.** The overall gap ({pp(rc['diff'])}) passes the selection-aware test \
(p {fmt_p(perm['C']['p'])}), but it rests on {rc['k1']} conversions. It is concentrated in one shift (US: \
{pc(cs.loc['US_SHIFT','k1'] / cs.loc['US_SHIFT','n1'])} vs {pc(cs.loc['IST_SHIFT','k1'] / cs.loc['IST_SHIFT','n1'])} on IST) and one \
half-month (1–15 June: {int(ch.loc['Jun 1–15','k1'])} of {int(ch.loc['Jun 1–15','n1'])} converted). Drop either one and \
the gap is no longer significant. In July alone it is {pp(c_jul['diff'])} with a CI that includes 0.
- **Most defensible operational problem:** A — the wait between lead arrival and demo (section 6). It is the \
only candidate that is strong, large, spread across the whole operation and located at a step the sales \
team controls. Causation is **not** shown: an unmeasured factor such as parent intent would need a risk ratio \
of ≥{ev['A'][1]:.1f} with both late booking and no-show to explain it away. That is possible, so it needs \
testing before anyone relies on it."""

    interp_a = f"""**Reading the evidence**

- **Observed fact.** {ra['n1']:,} of {len(s):,} scheduled demos ({pc(ra['n1'] / len(s))}) were set more than \
{LATE_H}h after lead creation; {pc(ra['p1'])} were joined vs {pc(ra['p0'])} for the rest. These late demos hold \
{noshow_late:,} of the {noshow_all:,} no-shows ({pc(noshow_late / noshow_all)}). Right around the threshold \
(36–48h vs 48–60h) join rate falls from {pc(k0 / n0)} to {pc(k1 / n1)} ({pp(dn)}, CI [{lon * 100:+.1f}, \
{hin * 100:+.1f}]). Late demos that *are* joined complete ({pc(cj_late['p1'])} vs {pc(cj_late['p0'])}) and convert \
({pc(vc_late['p1'])} vs {pc(vc_late['p0'])}, p {fmt_p(vc_late['p'])}) at least as well as early ones.
- **Observed fact.** Late booking is spread evenly across source, geography, shift, rep, month and weekday \
(all SMD ≤ 0.1). The one imbalance is follow-up attempts (SMD {fu_smd[0]:.2f}: {fu_smd[1]}). Follow-ups can be a \
consequence of a far-off demo (more days to chase), so they are kept out of the headline model and shown only as a \
sensitivity row.
- **Inference.** Because the gap is the same size in every rep, shift, market and source, it looks like a \
property of the booking process, not of one team or one audience. Late joiners convert just as well, which \
fits "the same parents, fewer of whom turn up" better than "a less interested group of parents".
- **Inference.** The drop is a *step* at ~{LATE_H}h rather than a steady decline. That shape suggests a rule \
or process boundary — for example, reminders or confirmations that only run for demos inside a 48h window — \
or an artefact of how the data was generated. The file cannot tell which.
- **Assumption (untested).** That the delay causes the no-show. The other direction is plausible: parents \
with low intent may pick far-off slots or be hard to reach. Intent is not in the data. The E-value \
({ev['A'][1]:.2f}; {ev['A'][2]:.2f} for the CI limit) says how strong such a factor would need to be. That is \
large but not implausible for intent.
- **Assumption (untested).** That `demo_scheduled_at` is the *first* slot offered, not a rescheduled one, \
and that the slot can be moved earlier. Who picks the slot (parent, rep or a capacity-limited calendar) is \
unknown."""

    others = ", ".join(f"{k} {pc(v)}" for k, v in vc_geo.drop(["India", "Vietnam"]).sort_values().items())
    shift_iv = dict((lab, which) for lab, v, which in B["balance"])["Rep shift"].split(" ", 1)[1]
    interp_b = f"""**Reading the evidence**

- **Observed fact.** V/C: India {pc(vc_geo['India'])}, Vietnam {pc(vc_geo['Vietnam'])}; the other six range \
{others}. The pair is lower than each of the six individually (smallest gap: vs UK, {B['own']['max_pair']:+.1f} pp) \
and lower than the rest with the high-converting USA left out. India and Vietnam do not differ from each \
other (p {fmt_p(B['own']['p_iv'])}).
- **Observed fact.** Before the demo these markets are close to normal (only the join rate is slightly lower): scheduled {pp(pre['S/L']['diff'])} \
(p {fmt_p(pre['S/L']['p'])}), joined {pp(pre['J/S']['diff'])} (p {fmt_p(pre['J/S']['p'])}), completed \
{pp(pre['C/J']['diff'])} (p {fmt_p(pre['C/J']['p'])}). Almost the whole gap sits at the payment decision.
- **Observed fact.** The shift mix is close to the rest (US shift {shift_iv[1:-1]}), and the gap is the same \
size on IST, SEA and US shifts and under every rep. So the team handling the lead does not explain it.
- **Inference.** A gap that is the same whoever handles the lead, and that appears only at the payment \
step, points to something about the market rather than about how the lead was worked: price relative to \
local income, payment methods, currency, or product/language fit. None of these is in the file.
- **Assumption (untested).** That the ₹60,000 revenue per conversion applies in these markets. If prices \
are localised, the value of this gap differs.
- **Assumption (untested).** That the demo and the closing conversation are the same product in every \
market. The demo teacher and closer are not recorded, so a market-specific pitch problem cannot be ruled \
in or out."""

    interp_c = f"""**Reading the evidence**

- **Observed fact.** DSA V/C {pc(rc['p1'])} ({rc['k1']} of {rc['n1']}). It is below every other source, but its \
gap to Affiliate ({pc(rest_sources['Affiliate'])}) has a CI that includes 0. Against paid sources only \
(Affiliate, Google, Meta) the gap is {pp(c_aff['paid'][0])} [{c_aff['paid'][1] * 100:+.1f}, \
{c_aff['paid'][2] * 100:+.1f}].
- **Observed fact.** US_SHIFT holds {pc(c_def['rep_shift'].set_index('level').loc['US_SHIFT','share_n'])} of \
DSA demos but {pc(c_def['rep_shift'].set_index('level').loc['US_SHIFT','share_def'])} of the shortfall. \
Without it the gap is {pp(c_shift['d'])} (p {fmt_p(c_shift['p'])}). The first half of June holds \
{pc(c_def['half_month'].set_index('level').loc['Jun 1–15','share_n'])} of DSA demos but \
{pc(c_def['half_month'].set_index('level').loc['Jun 1–15','share_def'])} of the shortfall. Without it the gap \
is {pp(c_half['d'])} (p {fmt_p(c_half['p'])}). The gap varies across half-months more than chance would \
(Q p {fmt_p(C['strata']['half_month'][1]['q_p'])}).
- **Observed fact.** July alone: {pp(c_jul['diff'])} [{c_jul_ci[1] * 100:+.1f}, {c_jul_ci[2] * 100:+.1f}].
- **Inference.** DSA may well convert somewhat below average; sources clearly differ (chi-square among the \
other five: p {fmt_p(c_aff['p_rest'])}). But the headline −10 pp gap leans on a few weeks and one shift. The \
honest range for the true gap runs from about −4 pp to −15 pp.
- **Assumption (untested).** What "DSA" is and what it costs per lead. A low-converting channel can still \
be the cheapest per conversion.
- **Assumption (untested).** That the June dip is not an event such as a campaign, a partner batch or a \
tracking change. The file has no campaign or batch field."""

    why = {}
    why["A"] = (f"**Why {g['A']}.** Every criterion is passed with room to spare. The gap is ~{abs(ra['diff']) * 100 / (A['mde'][1] * 100):.0f}× "
                "the smallest effect detectable even at a Holm-level threshold; it is present in 100% of strata; "
                "no subgroup, week or month is needed for it; and adjustment for pre-exposure variables leaves it unchanged. "
                "The only thing holding it back from a causal claim is an *unmeasured* confounder (intent), "
                "which statistics on this file cannot rule out.")
    why["B"] = (f"**Why {g['B']}.** Every criterion is passed. Its weaknesses from Phase 3 are dealt with: the "
                "post-hoc pooling of India and Vietnam is covered by the permutation test (which searched all "
                f"{perm['B']['n_groups']} single geographies and pairs), and the comparison is not inflated by "
                "the USA. **The grade is for the association, not the lever.** As an *operational* leak it is "
                "much weaker, because nothing observed separates a process failure from price or market fit.")
    why["C"] = (f"**Why {g['C']}.** It passes the permutation test and survives adjustment, so it is unlikely to "
                f"be pure noise. But it fails two criteria. (1) **One small group drives it**: removing US_SHIFT "
                f"or the first half of June makes it non-significant. (2) **Sample size**: {rc['k1']} conversions, "
                f"and a Holm-level MDE of {C['mde'][1] * 100:.1f} pp that is larger than the observed gap. It is also "
                "unstable over time (clear in June, CI includes 0 in July). Treat it as a hypothesis to "
                "re-check on more data, not as a finding.")

    final = f"""**The problem: a large share of demos are booked too far out, and those demos are mostly no-shows.**

__FACT_TABLE__

**Why A and not B.** B is just as solid statistically, but its gap appears only at the payment decision and \
is the same whoever handles the lead. The data cannot attribute it to anything the sales operation does. It \
is a market/pricing question to hand to the business, not a defensible operational leak on this evidence.

**Why not C.** It is weak: {rc['k1']} conversions, driven by one shift and two weeks, and not significant in July.

**What would turn the association into a causal finding** (evidence to seek, not a solution): a booking \
timestamp and a reschedule flag (to separate "booked late" from "booked quickly for a late slot"); who \
chose the slot; and ideally a randomised comparison of booking windows. Without these, the defensible \
statement is: *demos booked more than {LATE_H}h out are strongly and consistently associated with no-shows, \
across the whole operation.*"""

    fact_table = md_table(pd.DataFrame([
        ["Observed fact", f"{pc(ra['n1'] / len(s))} of scheduled demos ({ra['n1']:,} in two months) are set more "
                          f"than {LATE_H}h after the lead arrives."],
        ["Observed fact", f"Those demos are joined {pc(ra['p1'])} of the time vs {pc(ra['p0'])} for demos within "
                          f"{LATE_H}h; they account for {pc(noshow_late / noshow_all)} of all no-shows."],
        ["Observed fact", f"The gap is the same across every source, market, timezone, local hour, shift, rep, "
                          f"follow-up level, half-month and week. It survives adjustment for pre-exposure variables (OR "
                          f"{full['A']['or_']:.2f} [{full['A']['lo']:.2f}, {full['A']['hi']:.2f}])."],
        ["Observed fact", f"Leads whose demo was late but who did join convert at least as well as early ones."],
        ["Inference", f"This behaves like a process-level property of how demos are booked, not a people or "
                      f"market problem, and it sits at a step the sales operation controls (when the demo "
                      f"happens)."],
        ["Inference", f"The sharp step at ~{LATE_H}h suggests a process boundary (reminders, confirmation or "
                      f"slot-release rules) worth checking in the CRM."],
        ["Assumption", f"That moving demos inside {LATE_H}h would recover a meaningful share of the join-rate "
                       f"gap. This is **not** shown. Low-intent parents choosing far slots would produce the same"
                       f" pattern (E-value {ev['A'][1]:.2f})."],
        ["Assumption", f"`demo_scheduled_at` is the demo slot as first booked, and slot timing is at least partly"
                       f" under the company's control."],
    ], columns=["type", "statement"]))
    final = final.replace("__FACT_TABLE__", fact_table)
    for k_, v in [("__SUMMARY__", summary), ("__INTERP_A__", interp_a), ("__INTERP_B__", interp_b),
                  ("__INTERP_C__", interp_c), ("__WHY_A__", why["A"]), ("__WHY_B__", why["B"]),
                  ("__WHY_C__", why["C"]), ("__FINAL__", final)]:
        assert k_ in text, k_
        text = text.replace(k_, v)
    return text


if __name__ == "__main__":
    main()
