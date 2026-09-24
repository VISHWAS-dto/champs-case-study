# Late-Demo Rescue Sheet (Phase 9 prototype)

A browser page that turns the day's CRM export into a call list for reps. It lists every upcoming demo that was booked **more than 48h after the lead arrived**, with its **rescue deadline** (`created_at + 48h`) in the parent's local time. Half the rows go to reps (odd lead ID, the rescue arm) and half are held back untouched (even ID, the control arm), so the pilot can be measured fairly.

Design: [`results/phase_08_prototype_design.md`](../results/phase_08_prototype_design.md). Lever: [`results/phase_07_selected_lever.md`](../results/phase_07_selected_lever.md).

## What's here

```
prototype/
├── rescue_sheet.html          # the tool: open it in a browser
├── rescue_logic.js            # every rule, as pure functions (loaded by the page and the tests)
├── check_rescue_logic.py      # independent pandas re-implementation + acceptance checks
├── sample/
│   ├── case_export.csv        # the case CSV, used as the demo input
│   ├── rescue_outcomes_demo.csv  # SIMULATED outcome log (23 rows) to demo the Summary tab
│   └── sample_output.txt      # what check_rescue_logic.py prints
└── tests/
    ├── rescue_logic.test.js   # Node built-in test runner, no npm packages
    └── test_check_rescue_logic.py  # stdlib unittest
```

## Run the tool (nothing to install)

1. Double-click `rescue_sheet.html` (Chrome, Safari, Firefox or Edge). Keep `rescue_logic.js` in the same folder. The page works offline and the data never leaves the browser.
2. **1. CRM export**: pick `sample/case_export.csv`.
3. **2. Outcome log** (optional): pick `sample/rescue_outcomes_demo.csv` to see worked rows.
4. **Run as of**: set `2026-07-15 09:00` (the case data is historical; in daily use leave it at now).
5. Press **Build today's list**.

The **How to use** tab on the page has the same steps for analysts, reps and shift leads.

## Sample input → output

Input (`sample/case_export.csv`, run as of 2026-07-15 09:00):

```csv
lead_id,lead_source,geography,parent_timezone,created_at,demo_scheduled_at,rep_assigned,rep_shift,...
L104265,...,Vietnam,Asia/Ho_Chi_Minh,2026-07-13 09:13,2026-07-18 16:33,AD-07,IST_SHIFT,...
L102531,...,Australia,Australia/Sydney,2026-07-13 12:54,2026-07-17 00:38,AD-07,IST_SHIFT,...
```

Output on the **Daily list** tab:

| | count |
| --- | ---: |
| Upcoming demos booked >48h after lead | 92 |
| …deadline open (MOVE) / passed (CONFIRM) | 45 / 47 |
| Open rows: rescue / control | 27 / 18 |
| Open rescue rows by shift | IST 15 · US 10 · SEA 2 |

Rep **AD-07**, top of list:

| lead | geo | deadline (parent local) | left | current slot (parent local) | action |
| --- | --- | --- | ---: | --- | --- |
| L104265 | Vietnam | Wed 15 Jul, 16:13 | 0.2 h | Sat 18 Jul, 23:33 | MOVE |
| L102531 | Australia | Wed 15 Jul, 22:54 | 3.9 h | Fri 17 Jul, 10:38 | MOVE |

**Measurement** tab with no outcome log (an A/A check, since nobody was called in the case data): rescue 629 late demos, J/S 46.4%; control 656, J/S 47.4%; difference −1.0 pp, 95% CI −6.4 to +4.5 pp. The arms are balanced, as they should be.

The full terminal version of this output is in [`sample/sample_output.txt`](sample/sample_output.txt).

## Rules

All rules are in `buildRescueList()` in `rescue_logic.js`:

| rule | |
| --- | --- |
| Flag | demo booked · `demo_scheduled_at − created_at` > 48h · demo still in the future · lead created on or before "as of" |
| Deadline | `created_at + 48h` |
| Action | **MOVE** (offer a slot before the deadline) if the deadline hasn't passed, else **CONFIRM** (confirm the current slot live) |
| Arm | last digit of `lead_id` odd → RESCUE (shown to reps), even → CONTROL (never shown) |
| Order | MOVE before CONFIRM, then soonest deadline first |

Outcome codes: `moved_before_deadline`, `moved_after_deadline`, `confirmed_as_is`, `no_answer`, `cancelled`.

Week-4 verdict (Measurement tab, Phase 7 §6): **Scale** if the CI of rescue − control excludes zero and ≥80% of rescue rows were worked before their deadline. **Stop or pivot** if the CI includes zero with ≥80% completion. **Inconclusive** if completion is <80%.

## Check and test

From the repository root:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 prototype/check_rescue_logic.py                      # pandas version; exits 1 if any acceptance check fails
python3 prototype/check_rescue_logic.py my_export.csv --as-of "2026-07-20 09:00" --rep AD-03

node --test prototype/tests/rescue_logic.test.js             # 19 tests, needs Node 18+
python3 -m unittest discover -s prototype/tests -v           # 5 tests
```

The JS tests cover CSV parsing, time handling, each flag rule, sorting, summaries, the outcome log, the CI and the decision rule. They also reproduce the Phase 8 acceptance counts on the case CSV. The Python tests check that pandas reaches the same counts independently.

## Errors the tool handles

- Missing columns → a message naming them. Empty file or an unclosed quote → a message.
- Unreadable dates or lead IDs without a digit → the row is skipped and listed under "row(s) skipped". The rest of the file still loads.
- Unknown timezone → the time is shown in UTC and labelled.
- Outcome-log rows with unknown codes or bad timestamps → skipped and reported.
- Browser storage blocked (private window) → outcomes stay in memory for the session. Use **Download outcome log**.

## Known limits

- The export clock is assumed to be **UTC**. Flags and deadlines don't depend on it (they are differences), but the displayed local times do. The rep confirms the time with the parent on the call.
- The CRM has no booking timestamp, so a row can first appear after its deadline has passed (it then shows as CONFIRM).
- Outcomes are saved per browser (`localStorage`). If reps log on different machines, the analyst downloads each log and loads them one after another (later rows win).
- `sample/rescue_outcomes_demo.csv` is **simulated**, only to demo the tabs. The page shows a warning whenever it is loaded.
- Not built on purpose: CRM or calendar integration, messaging, logins, risk scoring (see Phase 8 §12).
