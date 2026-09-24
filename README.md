# champs-case-study

BrightChamps FDA take-home case: find where the demo funnel leaks, size it, choose one lever, and build a working prototype of it.

## Layout

```
BrightChamps_FDA_Case_Dataset.csv   # case data (5,000 leads, Jun–Jul 2026)
analysis/                           # one script per phase (phases 1–7); each writes to results/
results/                            # phase write-ups (phase_00 … phase_08) and figures/
prototype/                          # Phase 9: the Late-Demo Rescue Sheet (see prototype/README.md)
summary.txt                         # plain-language summary
```

## The finding in one line

39.8% of scheduled demos are booked more than 48h after the lead arrives, and they join at 46.9% vs 74.9%. The chosen lever (Phase 7) is a daily **rescue list**: reps offer those parents a slot before `created_at + 48h`. The list is measured against an untouched control half (odd vs even lead ID).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the analysis

```bash
python3 analysis/phase_01_data_audit.py        # …through phase_07_lever_charts.py
```

## Run the prototype

Open `prototype/rescue_sheet.html` in a browser. Nothing needs installing. Load `prototype/sample/case_export.csv`, set **Run as of** to `2026-07-15 09:00`, and press **Build today's list**. Details, sample output and limits are in [`prototype/README.md`](prototype/README.md).

Check and test:

```bash
python3 prototype/check_rescue_logic.py                  # pandas check of the Phase 8 acceptance counts
node --test prototype/tests/rescue_logic.test.js         # core logic (Node 18+, no npm packages)
python3 -m unittest discover -s prototype/tests -v       # Python check script
```

No API keys or secrets are used anywhere in this repo.
