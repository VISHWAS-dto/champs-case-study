# Phase 8 — Prototype Design: the Late-Demo Rescue Sheet

Inputs: `results/phase_00_assignment_understanding.md` (build rules), `results/phase_07_selected_lever.md` (the lever and its §4.1 mechanics, §6 measurement). A few counts were run on `BrightChamps_FDA_Case_Dataset.csv` to size the example (§7, §8). **Design only. Nothing is implemented in this phase.**

Labels as in earlier phases: **[D]** counted in the CSV, **[I]** inference, **[A]** assumption.

---

## 0. The prototype in one paragraph

A single HTML page, `rescue_sheet.html`, that runs in any browser with nothing to install. The ops analyst drops in the day's CRM export (same 12 columns as the case CSV). The page flags every upcoming demo booked more than 48h after the lead arrived, computes each one's **rescue deadline (`created_at + 48h`)** in the parent's local time, splits the rows into **rescue (odd lead ID)** and **control (even lead ID)**, and shows each rep their own rescue rows, soonest deadline first. Reps pick one outcome per row from a dropdown. A summary panel shows the shift lead what has been worked and what is about to expire. A second tab reads a later export plus the outcome log and reports join rate (J/S) by arm, which is the Phase 7 §6 measurement.

---

## 1. Technology choice

The build must *actually run*, open **without installing anything** (Phase 0 §5), and be ownable by a non-engineer.

| option | opens with nothing installed? | ownable by an ops analyst? | fit |
| --- | --- | --- | --- |
| Python script (CSV in → CSV out) | No: needs Python + pandas | Only by someone who codes | Good as a test harness, weak as the deliverable |
| Streamlit | No, unless hosted. Hosting adds an account and a deploy step | Needs Python to change | Over-built for one table |
| FastAPI | No; also needs a server | No | Over-engineered |
| Google Sheet + Apps Script | Yes, but only after copying the sheet into the reviewer's Google account and granting script permissions | Yes | Close second. Harder to hand over as a single file, and permission prompts make the demo fragile |
| AI agent | Depends on API keys | No | Nothing here needs judgement: the logic is a filter, a subtraction and a parity check |
| **Single-file HTML + JavaScript** | **Yes: double-click the file, or open a URL** | **Yes: one file, logic in one readable `<script>` block, no build step** | **Chosen** |

**Decision: one self-contained HTML file**, with no framework and no CDN dependencies, so it also works offline and the CRM data never leaves the analyst's laptop. Timezone conversion uses the browser's built-in `Intl.DateTimeFormat`, so no date library is needed.

One small **Python check script** sits beside it. It recomputes the key counts with pandas (already in `requirements.txt`), so the JavaScript logic can be verified against the Phase 4–7 numbers. The reviewer doesn't need it to use the tool.

---

## 2. User

| user | what they need from the tool | Phase 7 time budget |
| --- | --- | --- |
| **Ops / sales analyst** (primary operator, 1) | Load the export, produce the day's list, export the outcome log, run the weekly readout | ~15 min/day, 1 h/week |
| **Rep** (12: IST 5, US 5, SEA 2) | See *only my* rescue rows, most urgent first, with the parent's local time and a script; log one outcome per row | ~1 row/day, ~5 min each |
| **Shift lead** (3) | See mid-shift how many rows are worked and which are about to expire | ~10 min/shift |
| **Head of sales** | Week-4 readout: J/S rescue vs control, with CI | 15 min/week |

---

## 3. Problem

[D] 39.8% of scheduled demos (1,285 of 3,229) are set more than 48h after the lead arrived. They join at 46.9% vs 74.9% (−28.0 pp). The drop is a **step at 48h measured from lead creation**, so a demo only benefits if it is moved to a slot **before `created_at + 48h`** (Phase 7 §1).

Today nobody sees these demos as a list, nobody knows the deadline for each one, and nobody can tell whether contacting them helps. The prototype has to:
1. surface the right rows early enough to act on them;
2. give each row a hard deadline in a time the rep can say to the parent;
3. keep a clean, untouched control group;
4. capture what happened, so the pilot can be measured.

---

## 4. Input

**A. CRM export (CSV)**: the 12 columns of the case file. Only 7 are used by the daily list:

| column | used for |
| --- | --- |
| `lead_id` | holdout arm (last digit odd/even), row key |
| `created_at` | deadline = `created_at + 48h` |
| `demo_scheduled_at` | the late flag (gap > 48h); "demo still upcoming" check |
| `parent_timezone` | show deadline and slot in the parent's local time |
| `rep_assigned`, `rep_shift` | per-rep and per-shift views |
| `geography` | context for the rep on the card |
| `demo_joined` | **measurement tab only**, from a *later* export. Ignored in the daily view |

**B. Settings** (top of the page, with defaults):

| setting | default | why |
| --- | --- | --- |
| "Run as of" time | now (the browser clock). For the case data, a picker set to `2026-07-15 09:00` | The case data is historical. The demo needs a simulated "now" |
| Export clock | UTC | [D] Phase 1 §7: the clock is unknown. [A] UTC is assumed; the flag and deadline don't depend on it (they are differences), only the local-time display does |
| Late threshold | 48 h | From Phase 4. Editable but not expected to change |

**C. Outcome log (optional CSV)**: a previously downloaded log, so a new run carries forward rows already worked and the weekly readout can join outcomes to results.

---

## 5. Processing logic

Every rule below is a plain, stated rule from Phase 7 §4.1. There is no model and no scoring.

```
for each row in export:
    skip if demo_scheduled_at is blank                          # never booked
    gap_h        = hours(demo_scheduled_at − created_at)
    skip if gap_h <= 48                                         # not late
    skip if demo_scheduled_at <= as_of                          # already held; nothing to rescue
    deadline     = created_at + 48h
    hours_left   = hours(deadline − as_of)
    arm          = "RESCUE" if last digit of lead_id is odd else "CONTROL"
    action       = "MOVE"    if hours_left > 0                  # a slot before the deadline still helps
                   "CONFIRM" otherwise                          # past deadline: live confirmation only
    local times  = deadline and demo slot formatted in parent_timezone
    status       = outcome from log if present, else "TO DO"

daily list  = RESCUE rows, status TO DO, sorted by action (MOVE first), then deadline ascending
control log = CONTROL rows, recorded with the run timestamp, never shown to reps
```

**Outcome codes** (one dropdown per row, as in Phase 7 §4.1): `moved_before_deadline` · `moved_after_deadline` · `confirmed_as_is` · `no_answer` · `cancelled`. Each saved outcome also stores `logged_at`, so "worked before deadline" can be computed.

**Summary panel** (shift lead): per shift and per rep, rows due / worked / **% worked before deadline** (target ≥80%, Phase 7 §4.8) / count by outcome / rows expiring in the next 4h.

**Measurement tab** (weekly, Phase 7 §6):
- Inputs: a later export (with `demo_joined` filled in) plus the outcome log.
- Per arm: flagged n, joined n, J/S, and the difference rescue − control with a 95% CI (normal approximation for two proportions, the same method as Phase 4).
- Per outcome code: J/S next to the control arm (diagnostic only, and labelled as not causal).
- Guardrail: % of rescue rows worked before their deadline.
- Analysis is intent-to-treat: every rescue-arm row counts, whatever its outcome.

**Persistence**: outcomes are saved in the browser (`localStorage`) and can be downloaded or uploaded as `rescue_outcomes.csv`. [A] In a real rollout the analyst merges reps' logs, or the rows are pasted into a shared Google Sheet. The prototype deliberately stops at CSV.

---

## 6. Output

1. **Rep view**: filter by rep → cards or table rows with: lead ID, geography, **deadline (parent local time) + hours left**, current slot (parent local time), action badge (MOVE / CONFIRM), the call script with the fields filled in, and the outcome dropdown.
2. **Shift-lead summary**: the counts table from §5 and an "expiring in 4h, not worked" list.
3. **Downloads**: `rescue_list_<date>.csv` (all flagged rows including arm, deadline and action), `rescue_outcomes.csv` (log).
4. **Measurement tab**: J/S by arm with CI, J/S by outcome, completion guardrail, and a one-line verdict against the pre-registered rule (scale / stop / inconclusive).

---

## 7. Example input

> **Phase 14 update.** Row-level examples now come from the **synthetic** sample (`prototype/sample/demo_export.csv`), because the confidential case CSV is no longer in the repository. MOVE now also needs at least 3h before the deadline (otherwise CONFIRM). Counts on the case CSV are given where they are aggregate only.

Synthetic export, run as of **2026-07-15 09:00** (start of a shift), example rows:

```csv
lead_id,lead_source,geography,parent_timezone,created_at,demo_scheduled_at,rep_assigned,rep_shift,follow_up_attempts,demo_joined,demo_completed,converted
D51137,DSA,USA,America/New_York,2026-07-14 00:46,2026-07-22 03:59,AD-02,US_SHIFT,...
D80653,Meta,USA,America/New_York,2026-07-14 08:55,2026-07-18 04:54,AD-02,US_SHIFT,...
D50682,Google,USA,America/New_York,2026-07-06 09:55,2026-07-16 09:17,AD-02,US_SHIFT,...   ← even ID → control
```

(`demo_joined` / `demo_completed` / `converted` are present because the file is historical. The daily view ignores them, as they would be blank in a live export.)

---

## 8. Example output

**Run summary** for 2026-07-15 09:00 [D, counted from the case CSV, with the 3h MOVE rule]:

| | count |
| --- | ---: |
| Upcoming demos, slot >48h after lead | 92 |
| …≥3h to deadline (MOVE) | 43 |
| …<3h or deadline passed (CONFIRM only) | 49 |
| Open rows → rescue arm (odd) / control (even) | 25 / 18 |
| Rescue rows by shift (open): IST / US / SEA | 14 / 9 / 2 |

The 49 "CONFIRM only" rows are an artefact of running on a historical snapshot for the first time. In daily use each row is caught on the first run after booking, and [D] across June–July a 09:00 run finds on average **~42 rows with an open window (range 26–56)**, of which ~half go to reps.

**Rep view: AD-02 (US shift), top of list** (synthetic sample):

| lead | geo | deadline (parent local) | left | current slot (parent local) | action | outcome |
| --- | --- | --- | ---: | --- | --- | --- |
| D51137 | USA | Wed 15 Jul, 20:46 (America/New_York) | 15.8 h | Tue 21 Jul, 23:59 | MOVE | ▾ |
| D80653 | USA | Thu 16 Jul, 04:55 (America/New_York) | 23.9 h | Sat 18 Jul, 00:54 | MOVE | ▾ |

Local times assume the export clock is UTC [A]. The page shows this assumption beside every time and the rep confirms the time with the parent in the call.

Card script for D51137: *"We have an earlier slot for your child before Wed 15 Jul, 20:46 your time. Would [slot 1] or [slot 2] work?"* → if no: *"No problem, can I confirm you're all set for Tue 21 Jul, 23:59?"*

**Measurement tab: sanity check on the case data** (an A/A test, since nobody was called in June–July) [D]:

| arm | late demos | J/S |
| --- | ---: | ---: |
| rescue (odd ID) | 629 | 46.4% |
| control (even ID) | 656 | 47.4% |
| difference | | −1.0 pp (CI spans 0) |

This is what the tab should show when *no* intervention has run: the ID-parity split is balanced. Any gap that appears during the pilot can then be attributed to the rescue.

---

## 9. Workflow: how a BrightChamps employee would use it

| when | who | steps |
| --- | --- | --- |
| Start of each shift | Analyst | 1. Export scheduled demos from the CRM. 2. Open `rescue_sheet.html` and drop in the CSV (plus yesterday's outcome log). 3. Check the run summary. 4. Share the list: the page itself on a shared screen/drive, or `rescue_list_<date>.csv` into the shift's sheet |
| During shift | Rep | 1. Select own rep ID. 2. Work MOVE rows top-down (deadline order), then CONFIRM rows. 3. Offer a slot **before the deadline shown**. 4. Pick the outcome |
| Mid-shift | Shift lead | Open the summary panel. Chase any "expiring in 4h, not worked" rows |
| End of shift | Analyst | Download `rescue_outcomes.csv` and keep it as the day's log |
| Weekly (Mon) | Analyst → Head of sales | Load the latest export plus all outcome logs in the Measurement tab. Share J/S by arm, J/S by outcome and the completion guardrail |
| Week 4 | Head of sales | Apply the pre-registered rule: scale / stop / fix adoption (Phase 7 §6) |

Hand-over: the file has a short "How to use" panel at the top, and every rule in §5 sits in one clearly commented function, so another analyst can change the threshold or the outcome codes without reading the rest of the code.

---

## 10. How success is measured

Two levels: **the prototype works**, and **the lever works**.

**A. Prototype acceptance (checked at build time, on the case CSV)**

| check | expected |
| --- | --- |
| Late demos across the whole file (gap > 48h) | 1,285 of 3,229 [D, Phase 4] |
| Arm split of those 1,285 | 629 odd / 656 even |
| A/A J/S by arm | 46.4% / 47.4% |
| Run as of 2026-07-15 09:00 | 92 flagged, 45 open, 27 open rescue rows |
| Opens by double-click in Chrome/Safari/Firefox with no network | Yes |
| Python check script and page agree on every count above | Yes |
| A new analyst can produce a rep list from a fresh CSV using only the on-page help | Within 5 minutes |

**B. Lever success (the pilot, Phase 7 §6, pre-registered)**

| type | metric | baseline | target / rule |
| --- | --- | --- | --- |
| Primary | J/S rescue arm − control arm, 95% CI, after 4 weeks (~300/arm) | 0 (A/A above) | Planning case +12.3 pp (46.9% → ~59%) |
| Process | % rescue rows worked before deadline | n/a | ≥80% daily per shift |
| Process | % of rows still before deadline at first appearance | measured week 1 | tests [A] "bookings happen soon after lead creation" |
| Diagnostic | J/S by outcome vs control | — | separates H1 (moving helps) from H2 (intent) |
| Guardrail | C/J and V/C of rescue-arm joiners | 87.9% / 23.2% | not below control |
| Money | extra joins × 16.4% × ₹60,000 | — | ~₹63,000/month per +1 pp J/S (Phase 7) |

---

## 11. Project structure

```
prototype/
├── rescue_sheet.html          # THE deliverable. One file: HTML + CSS + JS, no dependencies.
│                              #   Tabs: Daily list · Summary · Measurement · How to use
├── sample/
│   ├── demo_export.csv        # SYNTHETIC export used as the demo input (Phase 14; the case CSV is not in the repo)
│   └── rescue_outcomes_demo.csv  # small example log (clearly marked SIMULATED) to demo the
│                              #   summary and measurement tabs
├── check_rescue_logic.py      # pandas re-implementation of §5; prints the §10A counts
└── README.md                  # what it is, how to open it, how to run a day, known limits
```

Inside `rescue_sheet.html`, the script is split into four clearly named parts:

| part | responsibility |
| --- | --- |
| `parseCsv()` | ~30-line CSV parser (handles quoted fields) |
| `buildRescueList(rows, asOf, settings)` | all of §5: flag, deadline, arm, action, local times. Pure function, no DOM |
| `summarise()` / `measure()` | shift-lead counts; J/S by arm with CI |
| `render*()` | tables, rep filter, dropdowns, downloads, `localStorage` |

**Build estimate**: ~2–3 hours (page ~250–350 lines, check script ~40 lines, README). This fits the Phase 7 §4.5 slot on Days 2–3 and the assignment's 3–4 hour total.

---

## 12. Deliberately out of scope

| not built | why |
| --- | --- |
| CRM or calendar integration, finding real free slots | Needs engineering; the rep picks the slot. Slot availability is checked with shift leads (Phase 7, Day 3) |
| Sending WhatsApp or email | That is Option 2/5. The rescue is a rep's live contact |
| Logins, a shared database, multi-user sync | CSV log + analyst merge is enough for a 4-week pilot at ~1 row/rep/day |
| Risk scoring or AI ranking | [D] No signal beyond the 48h flag (Phase 7, Option 4) |
| Dashboards beyond one summary table | Not needed to make the week-4 decision |

## 13. Known limits (to state in the README)

- [A] Export clock assumed UTC. Only the displayed local times depend on it, and the rep confirms the time in the call.
- [A] No booking timestamp exists, so "first seen" is approximated by the first run in which a row appears. Rows can reach the list after their deadline has already passed.
- `localStorage` is per browser. If two people log on different machines, the analyst must merge the downloaded logs.
- The simulated outcome log in `sample/` exists only to demonstrate the tabs. It is not evidence and is labelled as such on screen.
