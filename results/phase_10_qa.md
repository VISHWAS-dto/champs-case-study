# Phase 10: QA and validation

Scope: the Phase 9 prototype (`prototype/`), the Late-Demo Rescue Sheet. I tested it as a QA engineer, ran every test myself, fixed what I found and re-ran everything.

**Verdict: ready to demo.** After the fixes, all 61 checks pass: 27 JS unit tests, 9 Python tests, 25 browser end-to-end checks. The 8 Phase 8 acceptance counts also pass. The JS and pandas versions agree on 23,836 rows across 261 snapshots. I found and fixed 14 bugs. None of them changed the headline numbers.

---

## 1. Tests performed

| # | Area | How it was tested |
| --- | --- | --- |
| T1 | Existing suites | `node --test prototype/tests/rescue_logic.test.js`, `python3 -m unittest discover -s prototype/tests`, `python3 prototype/check_rescue_logic.py` (acceptance checks), diffed against `sample/sample_output.txt` |
| T2 | Headline numbers | Recomputed them with a separate pandas script straight from `BrightChamps_FDA_Case_Dataset.csv`, without the prototype code |
| T3 | JS vs pandas parity | Ran both implementations every 6h from 1 Jun 09:00 to 5 Aug 09:00 (261 snapshots, 23,836 flagged rows). Compared lead IDs, action, arm and hours left |
| T4 | Edge cases in the logic | Direct calls on out-of-range times, a blank timezone, duplicate IDs, a demo before creation, a MOVE with minutes left, a `__proto__` lead ID, lower-case `y/n`, a semicolon CSV, binary garbage, formula text |
| T5 | Python CLI edge cases | Lead ID without a digit, a blank result, an empty file, a directory as input, `--as-of ""`, `--as-of 2026-99-99` |
| T6 | The page, end to end | New `prototype/tests/e2e_browser.mjs` runs the real page in headless Chrome over the DevTools protocol, with no packages. It makes 25 checks (listed in §2) and takes screenshots |
| T7 | Fresh checkout | Cloned the repo into a temp dir and ran the documented commands exactly as written |
| T8 | Dependencies | Matched every import in `analysis/` and `prototype/` against `requirements.txt`, and compared `pip freeze` with it |
| T9 | Security and privacy | Rendered HTML/script text from CSV fields, logged every network request the page makes, checked what goes into `localStorage` and into downloads, grepped for secrets |
| T10 | Docs and assumptions | Checked the README steps, the known limits and the assumption tags ([A]/[D]/[I]) against Phases 7 and 8 |

## 2. Results against the 12 questions

| # | Question | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Does it start? | **Yes** | The page loads with no JS errors, `RescueLogic` loads, and "Run as of" defaults to now. The CLI exits with 0 |
| 2 | Does the main workflow work? | **Yes** | Load export → build → pick a rep → log an outcome → summary → measurement all work in the browser (e2e checks 3–12). Outcomes persist in `localStorage` with a timestamp |
| 3 | Are calculations correct? | **Yes, after fixes** | T2 reproduces 3,229 scheduled, 1,285 late (39.8%), J/S 46.9% late vs 74.9% on time, and the 92 / 45 snapshot. T3 has 0 mismatches in rows, action or arm. Hours left differ by at most 0.1 h, only when a value falls exactly on a rounding midpoint (JS rounds .x5 up, pandas rounds to even). The CI matches a hand calculation (unit test) |
| 4 | Normal input? | **Yes** | Case CSV at 2026-07-15 09:00 gives 92 flagged, 45/47, 27/18, IST 15 · US 10 · SEA 2. The AD-07 top rows match the README exactly |
| 5 | Missing input? | **Yes** | No file, empty "as of", blank or negative threshold, empty file, header only and missing columns each produce a one-line message naming the problem. A blank timezone is labelled "timezone missing" |
| 6 | Invalid input? | **Yes, after fixes** | Bad dates, impossible times (fixed), duplicate IDs (fixed), IDs without a digit, unknown timezones, unclosed quotes, semicolon CSVs (hint added), bad outcome logs (message fixed), and the CLI with a bad path or empty `--as-of` (fixed, was a traceback) |
| 7 | Are outputs understandable? | **Yes** | Screenshots reviewed. Each row shows the deadline and current slot in the parent's local time, hours left, a MOVE/CONFIRM badge with a filled-in script, and a one-line verdict. Two wording fixes: "row(s) skipped" became "need attention" (some rows are kept and only flagged), and a MOVE row can no longer show "passed" |
| 8 | Does it address the leak? | **Yes** | The leak (Phases 3–5) is demos booked >48h after the lead, which join at 46.9% vs 74.9%. The tool lists exactly those demos while they can still be moved (`created_at + 48h`). It sends half to reps and holds out the other half, so the effect on J/S can be measured (Phase 7 §6 decision rule). The A/A check on historical data is balanced (−1.0 pp, CI −6.4 to +4.5), as it should be |
| 9 | Can another person run it? | **Yes, after fixes** | The page needs only a browser. In a fresh clone the documented commands pass. The test file's own header command (`node --test prototype/tests/`) **failed** on Node 22+ and has been fixed |
| 10 | Unnecessary dependencies? | **One removed** | `seaborn` was pinned but never imported, so I removed it. The page has zero dependencies. The JS tests use only Node built-ins |
| 11 | Security or privacy problems? | **None open** | The page makes no network requests except its own two files (verified). CSV text is rendered as text (the XSS probe did not run). `localStorage` holds only `lead_id`, outcome and time. The data has no names, phones or emails. No secrets are in the repo. Fixed: formula injection in downloaded CSVs, and prototype pollution via a `__proto__` lead ID |
| 12 | Are assumptions documented? | **Yes** | UTC export clock, no booking timestamp, per-browser storage and simulated demo outcomes are in `prototype/README.md` → Known limits, the page's How to use tab, and Phase 8 [A] tags. One gap is added below (§6) |

**Browser end-to-end checks (25/25 pass):** page loads · no file → error · empty "as of" → error · build → 92, 45/47, 27/18, shifts · AD-07 rows match README · rep view filters · outcome saves with a timestamp · blank threshold after build doesn't break logging · an older log doesn't overwrite a newer outcome · demo log shows SIMULATED warning and summary · measurement verdict 629/656 · A/A verdict with no outcomes · clear needs two clicks · missing columns / semicolon / empty / header only / unclosed quote → messages · bad-date row reported and unknown timezone labelled · negative threshold → error · bad outcome log → correct message · HTML in CSV shown as text · no horizontal scroll at 390px · no external requests · no uncaught JS errors.

## 3. Bugs found

Severity: **High** = wrong numbers or lost data in normal use · **Med** = wrong result or crash on plausible bad input · **Low** = cosmetic, docs, hardening.

| ID | Sev | Where | Bug | How found |
| --- | --- | --- | --- | --- |
| B1 | Med | `rescue_logic.js` `parseTime` | `10:75` or `:99` seconds were silently rolled over into a different time instead of being rejected | T4 |
| B2 | Med | JS + Python | A row with <3 min to its deadline was MOVE in JS but CONFIRM in Python, because Python decided on the rounded hours. On the page the same row showed a MOVE badge next to "passed" | T4 / T5 |
| B3 | High | `rescue_sheet.html` | Loading an outcome log overwrote newer outcomes a rep had just set in the browser. Pressing **Build** again with the same log file silently reverted the rep's work | code review (e2e now guards it) |
| B4 | Med | `rescue_sheet.html` | After a build, blanking the threshold field and then logging an outcome threw an uncaught error. The outcome was saved but the screen didn't update, and the header showed the edited threshold instead of the one used | code review (e2e now guards it) |
| B5 | Med | `rescue_logic.js` + CLI | Duplicate `lead_id` rows were flagged twice (two calls to one parent) and counted twice in the measurement | T4 |
| B6 | Med | `rescue_logic.js` `readOutcomeLog` | An outcome logged for a CONTROL lead (holdout contamination) passed silently | T4 |
| B7 | Low | `rescue_logic.js` `readOutcomeLog` | A `__proto__` lead ID replaced the outcome map's prototype | T4 |
| B8 | Low | `rescue_logic.js` | A bad outcome log gave the message "Expected the CRM export with the 12 case-file columns" | T4 |
| B9 | Low | `rescue_logic.js` `formatLocal` | A blank timezone was labelled "unknown timezone " with an empty name | T4 |
| B10 | Low | Downloads | CSV cells starting with `=`/`+`/`@` would run as formulas when opened in Excel or Sheets | T9 |
| B11 | Low | `rescue_sheet.html` | **Clear saved outcomes** wiped the whole log on one click | code review |
| B12 | Med | `check_rescue_logic.py` | A lead ID without a digit, a directory as input, or `--as-of ""` crashed with a traceback. Blank `demo_joined` counted as "not joined", while JS leaves it out | T5 |
| B13 | Low | `tests/rescue_logic.test.js` | The header said `node --test prototype/tests/`, which fails on Node 22+ | T7 |
| B14 | Low | `requirements.txt` | `seaborn` was pinned but unused | T8 |

## 4. Fixes made

| ID | Fix | Test added |
| --- | --- | --- |
| B1 | `parseTime` rejects hour > 23, minute > 59, second > 59 | JS "parseTime rejects out-of-range…" |
| B2 | Python decides the action before rounding. JS never shows 0.0 h on a MOVE row (minimum 0.1). The page shows "passed" based on the action, not the rounded hours | JS "a MOVE row with minutes left…", Py `test_action_is_decided_before_rounding` |
| B3 | New `mergeOutcomes()`: per lead, the later `logged_at` wins, whatever order logs are loaded in. The page uses it | JS "mergeOutcomes…", e2e "older outcome log keeps the newer outcome" |
| B4 | The page stores the settings used for a build (`state.settings`). All re-renders use them | e2e "blank threshold after build…" |
| B5 | First row kept. Duplicates listed under "need attention" (JS) or warned and skipped (CLI). `measure()` counts each lead once | JS "duplicate lead IDs…", Py `test_bad_and_duplicate…` |
| B6 | Kept for intent-to-treat, but reported as "CONTROL lead was worked (holdout contamination; kept)" | JS "outcome log: … control leads flagged" |
| B7 | Outcome-log rows whose lead ID has no digit are rejected | same test |
| B8 | `checkColumns` takes a description, so the outcome-log error names the outcome-log columns. A semicolon-separated file gets a "save as comma-separated" hint | JS "semicolon-separated exports…", e2e |
| B9 | A blank zone is shown as UTC and labelled "timezone missing" | JS "a missing timezone is labelled…" |
| B10 | `toCsv` prefixes `'` to cells starting with `=` `+` `@` tab or CR. Negative numbers are untouched | JS "toCsv neutralises spreadsheet formulas…" |
| B11 | Two clicks within 4 s to clear. The first click changes the label to "Click again to delete all outcomes". This avoids a `confirm()` dialog | e2e "Clear … needs a second click" |
| B12 | `load()` skips lead IDs without a digit and duplicates, with warnings. A missing path or a directory gives "File not found" with exit 2. An empty `--as-of` gives exit 2. The A/A readout leaves out blank results (matching JS) and handles an empty arm | Py `test_bad_and_duplicate…`, `test_demos_without_a_result…`, `test_empty_as_of_and_directory…` |
| B13 | The header comment now gives the working command | T7 re-run |
| B14 | Removed from `requirements.txt` | — |

Also: the note label changed from "row(s) skipped" to "row(s) need attention", since contamination rows are kept. Outcome-log problems now stay visible after a rep logs an outcome (they used to vanish on re-render). Both READMEs were updated with the new behaviour, the test counts and the e2e command.

**Unchanged by the fixes:** the case CSV has no duplicates, bad IDs or edge-of-deadline rows, so every Phase 8 acceptance number and `sample/sample_output.txt` is byte-identical before and after.

## 5. Final test run (after fixes)

```
node --test prototype/tests/rescue_logic.test.js      → 27 pass, 0 fail
python3 -m unittest discover -s prototype/tests       → Ran 9 tests, OK
python3 prototype/check_rescue_logic.py               → 8/8 acceptance [PASS], exit 0, output identical to sample_output.txt
node prototype/tests/e2e_browser.mjs                  → 25/25 passed
JS vs pandas, 261 snapshots / 23,836 rows             → 0 mismatches (rows, action, arm)
```

## 6. Open observations (not bugs, left as designed)

- **The "% worked before deadline" denominator includes CONFIRM rows.** On a first run over a historical snapshot, 47 of 92 rows are already past their deadline, so the Summary tab shows red percentages whatever reps do. In daily use this goes away: each row is caught while it's still MOVE, per Phase 8 §10. It holds only under assumption [A] that bookings happen soon after the lead arrives (Phase 7 #18). If the pilot sees many rows arriving already as CONFIRM, report completion on MOVE-at-first-sight rows only. Otherwise the guardrail will read "Inconclusive" for a reason that has nothing to do with rep adoption.
- The simulated demo log (23 rows vs 629 rescue late demos) makes the Measurement verdict "Inconclusive, 3.7% completion". That is correct behaviour, and the page shows the SIMULATED warning.
- Column names are case-sensitive (`Lead_ID` is reported as missing). That's acceptable for a fixed CRM export.
- Outcomes live in one browser's `localStorage` (documented). A shared store is the first thing to add if the pilot scales.

## 7. Final demo steps

1. Open `prototype/rescue_sheet.html` in Chrome, Safari, Firefox or Edge by double-clicking it. Nothing needs installing, and nothing is uploaded.
2. Press **Load sample data** (SYNTHETIC leads, SIMULATED outcomes; the confidential case CSV is not in the repository). Or pick `prototype/sample/demo_export.csv` under **1. CRM export**, set **Run as of** to `15/07/2026 09:00` and press **Build today's list**.
   Expect: **45** upcoming late demos · **12 / 33** MOVE / CONFIRM · **6 / 6** rescue / control · IST 2 · US 3 · SEA 1.
3. Every MOVE row has at least 3h to its deadline; rows with less show CONFIRM ("too late to move").
4. **Rep** → `AD-02`. The top row is D51137 (USA), deadline *Wed 15 Jul, 20:46*, 15.8 h left, MOVE, with the script filled in. Set its outcome to *moved before deadline*. The row greys out and the outcome count goes up.
5. The red SYNTHETIC/SIMULATED warning is shown. Open **Summary** to see per-shift and per-rep completion against the 80% target.
6. **Measurement** → **Run readout** (after **Load sample data**, the pilot window is filled in). Primary = MOVE-eligible stratum from the first-seen register: rescue 164 vs control 174; verdict **Extend the pilot** (CI includes 0 and reaches above +3 pp). On the case CSV with nobody called (A/A, no register): rescue 629 at 46.4% vs control 656 at 47.4%, −1.0 pp (CI −6.4 to +4.5).
7. Optional: **Download rescue list** (the CSV reps would get), and **Clear saved outcomes** (click twice) to reset.
8. For reviewers, from the repo root:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   python3 prototype/check_rescue_logic.py
   node --test prototype/tests/rescue_logic.test.js
   python3 -m unittest discover -s prototype/tests -v
   node prototype/tests/e2e_browser.mjs      # needs Chrome; CHROME=/path/to/chrome to override
   ```
