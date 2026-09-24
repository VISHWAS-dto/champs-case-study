# Late-Demo Rescue Sheet (prototype)

A browser page that turns the day's CRM export into a call list for reps. It lists every upcoming demo whose **slot is more than 48h after lead creation**, with its **rescue deadline** (`created_at + 48h`) in the parent's local time. Half the rows go to reps (odd lead ID, the rescue arm). The other half are held back untouched (even ID, the control arm), so the pilot can be measured fairly.

**Live:** https://vishwas-dto.github.io/champs-case-study/prototype/rescue_sheet.html. Press **Load sample data**.

Design: [`results/phase_08_prototype_design.md`](../results/phase_08_prototype_design.md). Lever: [`results/phase_07_selected_lever.md`](../results/phase_07_selected_lever.md).

## What's here

```
prototype/
├── rescue_sheet.html          # the tool: open it in a browser
├── rescue_logic.js            # every rule, as pure functions (loaded by the page and the tests)
├── check_rescue_logic.py      # independent pandas re-implementation + acceptance checks
├── sample/                    # SYNTHETIC data only (the confidential case CSV is not in the repo)
│   ├── make_demo_data.py      # generates the three files below (seeded)
│   ├── demo_export.csv        # synthetic CRM export, same 12 columns as the case file
│   ├── rescue_outcomes_demo.csv  # SIMULATED outcome log
│   ├── demo_data.js           # the same sample bundled for the "Load sample data" button
│   └── sample_output.txt      # what check_rescue_logic.py prints
└── tests/
    ├── rescue_logic.test.js   # Node built-in test runner, no npm packages
    ├── e2e_browser.mjs        # drives the page in headless Chrome
    └── test_check_rescue_logic.py  # stdlib unittest
```

## Run the tool (nothing to install)

1. Open the live URL, or double-click `rescue_sheet.html` (Chrome, Safari, Firefox or Edge). Keep `rescue_logic.js` and `sample/` next to it. The page works offline and the data never leaves the browser.
2. Press **Load sample data**. It fills in the synthetic export, the simulated outcome log, the first-seen register, **Run as of** `2026-07-15 09:00` and the pilot window, then builds the list.
3. Look at **Daily list** (pick a rep, e.g. AD-02), **Summary** and **Measurement** (press **Run readout**).

To use real data: pick the day's export under **1. CRM export**, leave **Run as of** at now, and press **Build today's list**.

## Sample output (synthetic data, as of 2026-07-15 09:00)

| | count |
| --- | ---: |
| Upcoming demos, slot >48h after lead | 45 |
| ≥3h to deadline (MOVE) / less or passed (CONFIRM) | 12 / 33 |
| Open rows: rescue / control | 6 / 6 |

Rep **AD-02**, top of list:

| lead | geo | deadline (parent local) | left | current slot (parent local) | action |
| --- | --- | --- | ---: | --- | --- |
| D51137 | USA | Wed 15 Jul, 20:46 | 15.8 h | Tue 21 Jul, 23:59 | MOVE |
| D80653 | USA | Thu 16 Jul, 04:55 | 23.9 h | Sat 18 Jul, 00:54 | MOVE |

**Measurement** after **Load sample data**: the primary stratum is MOVE-eligible, rescue 164 vs control 174, and the verdict is **Extend the pilot**. The pilot effect in the sample is SIMULATED and is not evidence.

On the confidential case CSV (run locally, as of 2026-07-15 09:00), the tool flags 92 demos: 43 MOVE and 49 CONFIRM, with 25 / 18 open rescue / control rows. The A/A readout is rescue 629 at 46.4% vs control 656 at 47.4%, a difference of −1.0 pp (CI −6.4 to +4.5), so the arms are balanced.

## Rules

All rules are in `rescue_logic.js`:

| rule | |
| --- | --- |
| Flag | demo booked · `demo_scheduled_at − created_at` > 48h · demo still in the future · lead created on or before "as of" |
| Deadline | `created_at + 48h` |
| Action | **MOVE** (offer a slot before the deadline) if **at least 3h** remain; otherwise **CONFIRM** (confirm the current slot live) |
| Arm | last digit of `lead_id` odd → RESCUE (shown to reps), even → CONTROL (never shown) |
| Order | MOVE before CONFIRM, then soonest deadline first |
| First-seen register | Each time a list is built, every newly flagged row (both arms) is recorded with its first-seen time and action. This entry is never overwritten |

Outcome codes: `moved_before_deadline`, `moved_after_deadline`, `confirmed_as_is`, `no_answer`, `cancelled`.

**Measurement** (`measure()`, intent-to-treat):

- **Population:** every lead in the first-seen register, with its arm fixed at first listing. Without a register (e.g. historical data), the readout falls back to late demos in the export and says so.
- **Primary:** the **MOVE-eligible stratum** (first listed with ≥ 3h to the deadline). Secondary: all listed late demos.
- **Verdict** (minimum worthwhile effect +3 pp):
  - **Inconclusive, fix adoption first** if fewer than 80% of rescue rows were worked before their deadline.
  - Otherwise **Scale** if the CI's lower end is above 0.
  - **Stop** only if the CI's upper end is below +3 pp.
  - Otherwise **Extend**.

## Operating owner

The tool has no server, so the pilot needs three named roles. Before go-live, the shift lead fills in the names.

| Task | Owner | When | How |
| --- | --- | --- | --- |
| Export the daily CRM file (12 case columns, all demos booked in the last ~14 days) | **Sales-ops analyst** | Before each shift starts | CRM report → CSV. This is the only data input |
| Build the list and keep the first-seen register | **Sales-ops analyst** | Each shift start | Open the page **in the same browser every day**; the register lives there. Press **Build today's list**, then **Download rescue list** as the dated backup (it includes `first_seen_at` / `first_action`) |
| Distribute the list to reps | **Shift lead** | Shift start | Share the page on a shared screen, or send each rep their rows from the downloaded list |
| Log outcomes | **Reps** | During the call | One dropdown per row. If reps use their own machines, each clicks **Download outcome log** at shift end |
| Merge outcome logs | **Sales-ops analyst** | End of each shift | Load each rep's `rescue_outcomes.csv` under **2. Outcome log**. The later `logged_at` wins, and control-lead entries are flagged as contamination |
| Watch adoption | **Shift lead** | Mid-shift and end of shift | **Summary** tab: rows expiring in 4h, % worked before deadline per rep (target ≥ 80%) |
| Pull `demo_joined` results for measurement | **Sales-ops analyst** | Weekly; final readout at week 4 | Export the same report after the demos have happened (`demo_joined` filled). Load it, set the pilot window, and press **Run readout** on the **same browser** that holds the register |
| Audit the holdout | **Sales-ops analyst** | Weekly | Check CRM activity for calls on control (even-ID) late demos, and for rescue rows logged with no call |

## Check and test

From the repository root:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python3 prototype/check_rescue_logic.py                      # synthetic sample; exits 1 if any acceptance check fails
python3 prototype/check_rescue_logic.py my_export.csv --as-of "2026-07-20 09:00" --rep AD-03
node --test prototype/tests/rescue_logic.test.js             # 33 tests, needs Node 18+
python3 -m unittest discover -s prototype/tests -v           # 11 tests
node prototype/tests/e2e_browser.mjs                         # 28 browser checks, needs Node 22+ and Chrome (CHROME=… to override path)
python3 prototype/sample/make_demo_data.py                   # regenerate the synthetic sample (seeded)
```

The case-data acceptance tests (one in JS, one in Python) run only if `BrightChamps_FDA_Case_Dataset.csv` is at the repository root. Otherwise they are skipped.

## Errors the tool handles

- **Bad or unusable files:**
  - Missing columns → a message naming them.
  - An empty file or an unclosed quote → a message.
  - A semicolon-separated CSV (Excel in some locales) → the missing-column message says to re-save it as comma-separated.
- **Bad rows:** unreadable or impossible dates, lead IDs without a digit, and duplicate lead IDs are skipped and listed under "row(s) need attention". The rest of the file still loads.
- **Outcome logs:**
  - Unknown codes, bad timestamps and lead IDs without a digit are skipped and reported.
  - An outcome logged for a **control** lead is kept but flagged as contamination.
  - When logs overlap, the entry with the later `logged_at` wins, whatever order they are loaded in.
- **Timezones:** a missing or unknown timezone → the time is shown in UTC and labelled.
- **Downloads:** cells that start with `=`, `+` or `@` get a `'` prefix, so a spreadsheet won't run CRM text as a formula.
- **Clearing data:** **Clear saved outcomes** needs a second click within 4 seconds. It clears the outcomes and the first-seen register.
- **Blocked browser storage:** in a private window, data stays in memory for the session. Use the download buttons.

## Known limits

- **Clock:** the export clock is assumed to be UTC. Flags and deadlines don't depend on it, but the displayed local times do, so the rep confirms the time with the parent on the call.
- **No booking timestamp:** a row can first appear after less than 3h remain (it then shows as CONFIRM and falls outside the primary stratum).
- **Slots:**
  - Slot capacity inside 48h is not visible to the tool, so the rep checks the calendar.
  - The Day-3 go/no-go check confirms capacity per shift.
- **Storage:**
  - Outcomes and the register are saved per browser (`localStorage`); see the Operating owner table.
  - Using **Load sample data** in the analyst's working browser mixes synthetic rows into the register. Use it on a different browser or profile, or press **Clear saved outcomes** before live use.
- **Not built on purpose:** CRM or calendar integration, messaging, logins, risk scoring (see Phase 8 §12).
