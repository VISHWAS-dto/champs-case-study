# BrightChamps Case Study

Find the biggest leak in the BrightChamps demo funnel, put a rupee value on it, pick one fix that can go live in two weeks, and build a working prototype of that fix.

## Overview

BrightChamps sells kids' courses through a demo-led funnel: **lead → demo scheduled → demo joined → demo completed → paid**. The case provides 5,000 leads (1 Jun – 31 Jul 2026, 12 columns) and two given figures: **₹60,000 revenue per paying customer** and **₹900 marketing cost per lead**.

The work ran in 12 phases. Each phase has a script in `analysis/`, a write-up in `results/`, and figures in `results/figures/`. The one-page memo is in `memo/final_memo.pdf`.

| Deliverable | Answer |
| --- | --- |
| The leak | Demos booked **more than 48h after the lead arrives** are joined 46.9% of the time, against 74.9% for demos booked within 48h |
| The value | **≈ ₹7.8 lakh/month** (planning case), ≈ ₹17.7 lakh/month (ceiling) |
| The lever | A daily **Late-Demo Rescue list**: reps offer those parents a slot before `created_at + 48h` |
| The build | `prototype/rescue_sheet.html`, an offline single-page tool with a built-in randomised holdout |

## Business Problem

Only **7.2%** of leads pay (362 of 5,000). The analysis asked three questions:

1. At which step, and for which leads, is the funnel losing the most customers who could have been saved?
2. Does the pattern hold up under validation, or is it an artefact of searching many segments?
3. What is it worth, and what fix could the sales team launch in two weeks with no engineering?

| Stage | Leads | Step conversion | Dropped |
| --- | ---: | ---: | ---: |
| Lead | 5,000 | – | – |
| Demo scheduled | 3,229 | 64.6% | 1,771 never booked |
| Demo joined | 2,060 | 63.8% | 1,169 no-show |
| Demo completed | 1,786 | 86.7% | 274 left early |
| Paid | 362 | 20.3% | 1,424 did not buy |

## Key Finding

**40% of scheduled demos are booked more than 48h after the lead arrives, and those parents are far less likely to show up.**

| | Demos | Join rate (J/S) |
| --- | ---: | ---: |
| Booked ≤ 48h after lead | 1,944 | **74.9%** |
| Booked > 48h after lead | 1,285 (39.8%) | **46.9%** |
| Difference | | **−28.0 pp** (95% CI −31.3 to −24.7) |

Evidence:

- **It is a step change, not a slope.** The join rate is 74–80% in every 12-hour bin up to 48h, then falls to 42–53% and stays flat. A demo 3 days out does about as well as one 7 days out.
- **It appears in every subgroup.** Same direction in every lead source, country, shift, rep, follow-up count, half-month and week. Removing any single group moves the gap by at most 1.6 pp.
- **It survives adjustment.** Controlling for all measured variables gives an odds ratio of 0.27.
- **It is not a search artefact.** The 48h cut was found by scanning thresholds, so the scan was re-run on 5,000 shuffled copies of the data. None came close (observed |z| = 16.2 vs a 95th percentile of 2.65; p < 0.001).
- **It is concentrated.** These demos are 40% of scheduled demos but **58% of all no-shows**.
- **The loss happens at the join step only.** Late-booked parents who do join complete (87.9%) and convert (23.2%) at least as well as everyone else.

Two other candidates were tested and not chosen:

| Candidate | Result | Why not chosen |
| --- | --- | --- |
| India + Vietnam pay less after the demo (11.2% vs 23.4%) | Strong association (p < 0.001) | Same across every rep and shift. Looks like price or market fit, not something the sales process controls |
| DSA leads pay less after the demo (11.1% vs ~21%) | Weak | Only 20 paying customers. Most of the gap comes from one shift and the first two weeks of June |

## Financial Impact

| Monthly figure | ₹ |
| --- | ---: |
| Actual revenue (362 × ₹60,000 ÷ 2 months) | 108.6 lakh |
| Marketing spend (5,000 × ₹900 ÷ 2 months) | 22.5 lakh |
| **Modeled upside, planning case** | **7.8 lakh** |
| Modeled upside, ceiling | 17.7 lakh |

**Planning case:**
`1,285 late demos × 24.65 pp (low end of the CI) × 50% causal share × 16.4% customers per joiner ≈ 26 customers × ₹60,000 = ₹15.6 lakh over 2 months ≈ ₹7.8 lakh/month`

**Ceiling:** the whole 28 pp gap closes → 360 extra joins → 310 completions → 59 customers → ₹35.4 lakh over 2 months.

Assumptions behind the number:

- Extra joiners go on to complete and convert at the observed baseline rates.
- **50% causal share** is a judgment call, not a measurement. At 25% the planning case falls to ₹3.9 lakh/month.
- Each percentage point of join-rate lift on late demos is worth about **₹63,000/month**.
- The ₹900 per lead is already spent, so it is not deducted. Recovering the same 59 customers by buying more leads would cost about ₹7.3 lakh in marketing.
- These are **revenue, not profit**, and a **modeled opportunity, not a proven loss**.

The shortcut "every late-booked non-buyer × ₹60,000" (= ₹6.97 crore) was rejected. Even parents booked on time only pay about 12% of the time.

## Proposed Intervention

**The daily Late-Demo Rescue list.**

1. Each morning, every shift gets a list of upcoming demos that were booked more than 48h after the lead arrived.
2. The owning rep calls or WhatsApps the parent and offers a slot **before the rescue deadline, `created_at + 48h`**.
3. If the deadline has passed or the parent won't move, the rep confirms the current slot live.
4. Leads with an **odd** ID go to reps (rescue arm). Leads with an **even** ID are left untouched (control arm), so the effect can be measured from day one.

The deadline matters. The join rate is flat past 48h, so moving a demo from day 5 to day 3 gains nothing.

**Why this one:**

- It targets exactly the population and the boundary where the gap sits.
- It is live in **about 5 working days** with no engineering: an existing CRM export plus a sheet.
- The load is **about 1 call per rep per day** (≈21 late demos a day across 12 reps, half held back).
- The built-in holdout turns the correlation into a causal test.
- It is useful whichever explanation is true. Moving the demo tests the wait, and the confirmation call reveals the parent's intent.

**Rejected:**

| Option | Reason |
| --- | --- |
| 48h default booking rule | Easy to game ("parent asked"). Changes the reps' core task. Hard to measure fairly |
| WhatsApp reminders for >48h demos | Only helps if late demos currently get fewer reminders, which nobody has checked. Template approval risks the 2-week launch |
| No-show risk score | Nothing to rank: past 48h all late demos look the same, and every row can already be worked |
| AI WhatsApp rebooking agent | 10–15 working days. Needs CRM/calendar integration. Highest brand risk |

**Pilot:** 4 weeks, about 300 demos per arm, enough to detect an ~11.5 pp lift. The decision rule is set in advance:

| Result | Decision |
| --- | --- |
| CI of (rescue − control) J/S excludes zero, and ≥ 80% of rows worked before the deadline | **Scale** |
| CI includes zero, and ≥ 80% of rows worked | **Stop or pivot** |
| < 80% of rows worked | **Inconclusive: fix adoption first** |

## Prototype

**`prototype/rescue_sheet.html`** is the Late-Demo Rescue Sheet. It is one HTML page with no install and no network calls, and the data never leaves the browser.

What it does:

- Loads the CRM export (CSV) and flags every upcoming demo booked more than 48h after its lead.
- Computes each row's **rescue deadline** and current slot in the **parent's local time**.
- Marks each row **MOVE** (deadline still open) or **CONFIRM** (deadline passed).
- Splits rows into rescue (odd ID) and control (even ID), and shows reps only the rescue arm.
- Sorts by deadline and filters by rep. Each row has a filled-in call script.
- Logs outcomes in one click (`moved_before_deadline`, `moved_after_deadline`, `confirmed_as_is`, `no_answer`, `cancelled`).
- **Summary** tab: % of rows worked per shift. **Measurement** tab: rescue vs control J/S with a 95% CI and the week-4 verdict.

Supporting files:

- `rescue_logic.js` holds every rule as pure functions. The page and the tests both use it.
- `check_rescue_logic.py` is an independent pandas re-implementation of the same rules, used to cross-check the numbers.

**QA (Phase 10):** 61 automated checks pass (27 JS unit, 9 Python, 25 headless-browser end-to-end). The JS and pandas versions agree on 23,836 flagged rows across 261 snapshots. 14 bugs were found and fixed; none changed the headline numbers. Full details are in [`prototype/README.md`](prototype/README.md) and [`results/phase_10_qa.md`](results/phase_10_qa.md).

## Project Structure

```
.
├── BrightChamps_FDA_Case_Dataset.csv        # case data: 5,000 leads, Jun–Jul 2026
├── BrightChamps_FDA_Take_Home_Case_CANDIDATE.pdf  # the case brief
├── requirements.txt                         # pinned Python packages
├── summary.txt                              # plain-language log of every phase
├── analysis/                                # one script per phase; each writes to results/
│   ├── phase_01_data_audit.py               # schema, blanks, duplicates, funnel order
│   ├── phase_01_audit_charts.py             # data-audit figures
│   ├── phase_02_funnel_analysis.py          # stage counts and drop-offs
│   ├── phase_03_leak_analysis.py            # 204-test segment screen, candidate leaks
│   ├── phase_04_leak_validation.py          # subgroup, adjustment and permutation checks
│   ├── phase_05_financial_impact.py         # counterfactual funnel and ₹ sizing
│   ├── phase_06_intervention_charts.py      # five fix options compared
│   └── phase_07_lever_charts.py             # chosen lever, workload, pilot plan
├── results/
│   ├── phase_00 … phase_10 *.md             # write-up for each phase (numbers and formulas)
│   └── figures/phase_01 … phase_07/         # all PNG charts
├── prototype/
│   ├── rescue_sheet.html                    # the tool: open in a browser
│   ├── rescue_logic.js                      # all business rules (pure functions)
│   ├── check_rescue_logic.py                # independent pandas check + CLI
│   ├── README.md                            # prototype guide, rules, error handling, limits
│   ├── sample/                              # demo input, SIMULATED outcome log, sample output
│   └── tests/                               # JS unit, Python unit, headless-browser e2e
└── memo/
    ├── final_memo.md                        # one-page memo (source)
    └── final_memo.pdf                       # one-page memo (deliverable)
```

## How to Run

Requirements: Python 3.11+ (developed on 3.14), Node 18+ for the JS tests, Node 22+ and Chrome for the browser test. The prototype page needs only a browser.

**1. Set up Python**

```bash
git clone <repo-url> && cd <repo-folder>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Reproduce the analysis** (each script rewrites its `results/` file and figures)

```bash
python3 analysis/phase_01_data_audit.py
python3 analysis/phase_01_audit_charts.py
python3 analysis/phase_02_funnel_analysis.py
python3 analysis/phase_03_leak_analysis.py
python3 analysis/phase_04_leak_validation.py     # 5,000-shuffle permutation test, seed 20260923
python3 analysis/phase_05_financial_impact.py
python3 analysis/phase_06_intervention_charts.py
python3 analysis/phase_07_lever_charts.py
```

**3. Run the prototype**

```bash
open prototype/rescue_sheet.html        # macOS; on other systems, open the file in any browser
```

**4. Run the tests**

```bash
python3 prototype/check_rescue_logic.py                  # acceptance checks; exits 1 on any failure
node --test prototype/tests/rescue_logic.test.js         # 27 JS unit tests
python3 -m unittest discover -s prototype/tests -v       # 9 Python tests
node prototype/tests/e2e_browser.mjs                     # 25 browser checks (CHROME=<path> to override)
```

No API keys or secrets are used anywhere in this repository.

## Example

**In the browser:**

1. Open `prototype/rescue_sheet.html`.
2. Under **1. CRM export**, choose `prototype/sample/case_export.csv`.
3. Optional: under **2. Outcome log**, choose `prototype/sample/rescue_outcomes_demo.csv` (simulated) to see worked rows.
4. Set **Run as of** to `2026-07-15 09:00`, then press **Build today's list**.

The **Daily list** tab shows:

| | Count |
| --- | ---: |
| Upcoming demos booked > 48h after lead | 92 |
| Deadline open (MOVE) / passed (CONFIRM) | 45 / 47 |
| Open rows: rescue / control | 27 / 18 |
| Open rescue rows by shift | IST 15 · US 10 · SEA 2 |

Rep **AD-07**, top of the list:

| Lead | Country | Deadline (parent local) | Hours left | Current slot (parent local) | Action |
| --- | --- | --- | ---: | --- | --- |
| L104265 | Vietnam | Wed 15 Jul, 16:13 | 0.2 | Sat 18 Jul, 23:33 | MOVE |
| L102531 | Australia | Wed 15 Jul, 22:54 | 3.9 | Fri 17 Jul, 10:38 | MOVE |

**From the command line:**

```bash
python3 prototype/check_rescue_logic.py prototype/sample/case_export.csv --as-of "2026-07-15 09:00" --rep AD-07
```

```
Run as of 2026-07-15 09:00 on case_export.csv
  upcoming demos booked >48h after lead : 92
  ...deadline open (MOVE)                  : 45
  ...deadline passed (CONFIRM)             : 47
  open rows rescue / control               : 27 / 18

Rep view AD-07 (top 5, deadline in export clock):
  L104265  Vietnam      deadline 2026-07-15 09:13     0.2 h  MOVE
  L102531  Australia    deadline 2026-07-15 12:54     3.9 h  MOVE
  ...
A/A readout (all late demos in the file, nobody was called):
  RESCUE   n=629   J/S=46.4%
  CONTROL  n=656   J/S=47.4%
  difference -1.0 pp, 95% CI -6.4 to +4.5 pp
```

The A/A readout shows the odd/even split is balanced on historical data, as it should be before anyone is called.

## Results

**Summary**

1. The data is clean: no duplicates, no invalid values, no broken funnel order. The only blanks are `demo_scheduled_at` (35.4%, meaning no demo booked).
2. The largest recoverable leak is at the **join** step, driven by demos booked more than 48h after the lead (−28.0 pp join rate, 58% of no-shows).
3. The finding survives every validation check applied. It is still a **correlation**; the pilot's holdout is what will test cause.
4. Modeled value: **≈ ₹7.8 lakh/month** planning case, ≈ ₹17.7 lakh/month ceiling.
5. The chosen lever, the Late-Demo Rescue list, is live in ~5 days and costs about one call per rep per day.
6. A working, tested prototype reproduces every headline number from the raw CSV.

**Figures**

*Phase 1: data audit* (`results/figures/phase_01/`)

| Figure | What it shows |
| --- | --- |
| `01_data_health.png` | 5,000 rows, 12 columns, **0 hard errors**. `demo_scheduled_at` is the only column with blanks (35.4%). The 2 timestamp columns carry no timezone |
| `02_funnel.png` | 5,000 → 3,229 → 2,060 → 1,786 → 362. The two weakest steps are scheduled→joined (64%) and completed→paid (20%) |
| `03_lead_source.png` | Meta (42%) and Google (24%) supply two-thirds of leads. Referral is smallest (5.5%) |
| `04_geography.png` | USA is a third of leads (33%), then Vietnam (16%), UK (11%) and India (10%). Each country maps to exactly one timezone |
| `05_reps_by_shift.png` | 12 reps, each on one shift: US (5 reps, 2,195 leads), IST (5, 2,078), SEA (2, 727). Load per rep ranges from 333 to 497 leads |
| `06_leads_per_day.png` | Steady inflow on all 61 days (min 62, median 82, max 101). No gaps or spikes that would distort rates |
| `07_created_to_demo_gap.png` | Median 27h from lead to demo, but the distribution is **bimodal**: a large peak under 36h and a second hump at 72–130h. This second group became the leak |
| `08_follow_up_attempts.png` | 0–9 attempts per lead, mostly 1–2. What counts as an attempt is not defined in the data |
| `09_hour_by_geography.png` | Leads arrive evenly across all 24 stored hours in every country. No day/night pattern, which suggests the clock is UTC or similar, not local time |

*Phase 2: funnel* (`results/figures/phase_02/`)

| Figure | What it shows |
| --- | --- |
| `01_funnel_dropoff.png` | Losses by step: 1,771 never booked, **1,169 no-shows**, 274 left early, 1,424 completed without paying. Drop-off counts are people, not lost revenue |

*Phase 3: finding the leak* (`results/figures/phase_03/`)

| Figure | What it shows |
| --- | --- |
| `01_segment_rate_heatmap.png` | Step rates for every source, country, rep, shift and follow-up band against the overall rate. The strongest red cells are conversion after the demo for India (9.7%), Vietnam (12.2%) and DSA (11.1%). Shifts are almost uniform |
| `02_join_rate_by_gap.png` | **The key chart.** Join rate is 74–80% in every bin up to 48h, then drops to 35–53% in every bin after. The break is sharp at 48h, not a gradual decline |
| `03_gap_effect_within_subgroups.png` | The ≤48h vs >48h gap appears inside every follow-up band, country, shift and source, so no single segment explains it |
| `04_post_demo_conversion.png` | Conversion after the demo with 95% intervals. India, Vietnam and DSA sit clearly below the 20.3% average; Referral and Organic sit above |

*Phase 4: validation* (`results/figures/phase_04/`)

| Figure | What it shows |
| --- | --- |
| `01_forest_A.png` | Candidate A (late demo): every one of ~40 subgroup intervals lies well left of zero, clustered around −28 pp. **Consistent everywhere** |
| `02_forest_B.png` | Candidate B (India + Vietnam): mostly negative around −12 pp across reps and shifts, with wider intervals. The association is real, but it does not depend on who sells |
| `03_forest_C.png` | Candidate C (DSA): many intervals cross zero, and the effect is concentrated in US shift and early June. **Weak** |
| `04_permutation_tests.png` | Re-running each search on 5,000 shuffled datasets: A (16.2) and B (5.6) are far beyond anything chance produced. C (3.2) clears the 95th percentile (2.28) but by much less |

*Phase 5: financial impact* (`results/figures/phase_05/`)

| Figure | What it shows |
| --- | --- |
| `01_late_demo_counterfactual_funnel.png` | The 1,285 late demos observed vs joined at the ≤48h rate: +360 joins → +310 completions → **+59 customers** (ceiling, ₹35.4 lakh over 2 months) |
| `02_monthly_money.png` | Scale check: the ₹7.8 lakh planning case is ~7% of monthly revenue (₹108.6 lakh). The ceiling is ₹17.7 lakh. Both are marked as modeled, not lost |
| `03_sensitivity.png` | Monthly value across gap size (24.7 / 28.0 / 31.3 pp) × causal share (25–100%): ₹3.9 lakh to ₹19.8 lakh. The causal share moves the answer far more than the gap estimate |

*Phase 6: intervention options* (`results/figures/phase_06/`)

| Figure | What it shows |
| --- | --- |
| `01_where_options_act.png` | Join rate is ~75% below 48h and flat at ~47% above it. Options 1, 3 and 5 move demos across the line. Option 2 works on demos that stay late. Option 4 has little to rank past 48h |
| `02_launch_timeline.png` | Options 1, 3 and 4 launch in 3–6 days, option 2 in 7–10. Only the AI agent (10–15 days) exceeds the two-week limit |
| `03_option_scorecard.png` | Side-by-side ratings. The rescue sheet has no high-risk cells. The booking rule has high adoption risk; the AI agent is slow, needs engineering and is high-risk |
| `04_holdout_power.png` | Smallest detectable lift vs pilot length at 21 late demos/day: 16.3 pp at 2 weeks, 11.5 pp at 4 weeks. The 12.3 pp planning case becomes detectable at **~3.5 weeks**, hence a 4-week pilot |

*Phase 7: selected lever* (`results/figures/phase_07/`)

| Figure | What it shows |
| --- | --- |
| `01_rescue_deadline.png` | Why the deadline is `created_at + 48h`: a demo moved inside it joins like an on-time demo. A demo moved but still past 48h gains nothing. The typical late demo is at 104h |
| `02_lift_to_money.png` | Each pp of join-rate lift ≈ ₹63,000/month. The planning case (+12.3 pp → ₹7.8 lakh) sits just above the 4-week detection floor (11.5 pp). The 25% causal case (+6.2 pp) would not be detectable |
| `03_rep_workload.png` | After the 50% holdout, load is 0.74–0.93 rescue rows per rep per day in every shift, about 4–5 minutes |
| `04_pilot_timeline.png` | Set-up in 4 working days, live on day 5 (five days inside the two-week limit), verdict after a 4-week measured pilot |

## Assumptions & Limitations

**Assumptions**

- ₹60,000 revenue per customer and ₹900 per lead are taken as given by the case.
- The export clock is **UTC**. Flags and deadlines are differences between two timestamps, so they don't depend on this; the displayed local times do.
- A blank `demo_scheduled_at` means no demo was booked.
- Extra joiners from the fix would complete and convert at the observed baseline rates.
- The **50% causal share** in the planning case is a judgment, not a measurement.
- About 5 minutes per rescue call, and enough free demo slots inside 48h in each shift. Slot capacity must be checked before go-live.

**What the dataset cannot prove**

- **Cause.** Late booking and no-shows go together, but less-keen parents may simply choose later slots. Only the randomised holdout in the pilot can separate the two.
- **Actual financial loss.** The ₹ figures are modeled revenue opportunity, not profit and not a proven loss. Running cost of the fix is unknown.
- **Why 35% of leads never book.** No column explains it, so this stage was not sized.
- **Why India and Vietnam convert less.** Price, market fit and sales process cannot be told apart.
- **Reminders today.** The data does not show whether late demos currently get fewer reminders, so the reminder option could not be evaluated.
- **Cancellations vs reschedules vs no-shows** are all recorded as "not joined".
- **Booking time.** The CRM has no booking timestamp, so a row can first appear after its deadline has passed (it then shows as CONFIRM).
- **Data freshness.** The extract date is unknown. Late-July leads may still be mid-funnel (6.6% paid vs 7.3% earlier).
- **Definitions.** "Follow-up attempt", shift working hours and "DSA" are not defined in the case.
- **Scope.** Two months of data, one company. `prototype/sample/rescue_outcomes_demo.csv` is **simulated** and only demonstrates the tabs.

## AI Tools Used

| Tool | Used for |
| --- | --- |
| **Claude Code** (Anthropic, model Claude Opus 5.5), in the terminal | Reading and summarising the case PDF (Phase 0) · writing the analysis scripts and figures for Phases 1–7 (audit, funnel, segment screen, validation incl. permutation tests, ₹ sizing, option and lever charts) · drafting the phase write-ups in `results/` and `summary.txt` · designing and building the prototype (`rescue_sheet.html`, `rescue_logic.js`, `check_rescue_logic.py`) and its tests · QA in Phase 10 (headless-browser e2e test, bug finding and fixes) · drafting the one-page memo and this README |

How AI output was controlled:

- Every number in the memo and this README comes from a script in this repository and can be regenerated with the commands above. No figure was typed in by hand.
- Key numbers were cross-checked by two independent implementations (JS and pandas) and a separate recomputation from the raw CSV (Phase 10).
- Judgment calls (the 50% causal share, the choice of lever, the pilot decision rule) are labelled as judgments, not data.
- The prototype contains no AI or LLM calls at runtime.
