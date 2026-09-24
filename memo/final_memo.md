# BrightChamps: Late-Demo Rescue

5,000 leads, 1 Jun–31 Jul 2026 · ₹60,000 per customer and ₹900 per lead, as given · **Live prototype:** [vishwas-dto.github.io/champs-case-study/prototype/rescue_sheet.html](https://vishwas-dto.github.io/champs-case-study/prototype/rescue_sheet.html) (press *Load sample data*)

## 1. The leak
**40% of scheduled demos have a slot more than 48h after lead creation, and those parents show up far less often.** Of 3,229 scheduled demos, 1,285 (39.8%) are late. They are joined **46.9%** of the time, against **74.9%** within 48h (−28.0 pp, 95% CI −31.3 to −24.7) and hold 58% of all no-shows. The gap holds in every source, country, shift, rep and week, and after adjusting for pre-exposure variables (OR 0.29). Late parents who do join complete and convert as well as others, so the loss is at the join step. **This is a correlation, not proven cause:** less-keen parents may simply pick later slots. `demo_scheduled_at` is read as the demo slot (the file has no booking time).

| Drop (common basis) | Lost | Benchmark gap | Ceiling/month | Selected? |
|---|---|---|---|---|
| Never booked | 1,771 leads | none (S/L 57–67% everywhere) | not sizable | No: nothing in the data to target |
| **No-show, slot >48h** | 1,285 demos | **28.0 pp** vs ≤48h | **₹17.7 lakh** | **Yes:** sales ops set the slot; 2-week fix |
| Left demo early | 274 joiners | none (C/J 81–89%) | not sizable | No: small and flat |
| No purchase, India+Vietnam | 464 completers | 12.2 pp vs other geos | ₹17.0 lakh | No: same for all reps/shifts (price, fit) |

## 2. Financial impact
**Leak ≈ ₹7.8 lakh/month modeled causal value (ceiling ₹17.7 lakh). The lever captures less: ≈ ₹1.9 lakh/month (illustrative).**
```
Leak:  1,285 × 24.65 pp (CI low end) × 50% causal × 16.4% per on-time joiner ≈ 26 × ₹60k ÷ 2 months
Lever: reach (80% worked × 60% reached) × 50% accept × 12.3 pp ≈ +3.0 pp J/S × ₹63k per pp/month
```
The capture rates and the 50% causal share are **assumptions, not data** (at a 25% share, the leak is ₹3.9 lakh/month). These figures are revenue, not profit. The ₹900 per lead is sunk, so it is not deducted.

## 3. The lever
**A daily Late-Demo Rescue list.** Each shift gets the upcoming demos whose slot is more than 48h after lead creation. The owning rep calls or WhatsApps the parent and offers a slot before the **rescue deadline, `created_at + 48h`**. If less than 3h is left, or the parent won't move, the rep confirms the current slot live. Leads with an odd ID go to reps; leads with an even ID are an untouched control.

## 4. Why this lever
It acts on exactly the population and the boundary where the gap sits, at about 1 call per rep per day (≈21 late demos a day across 12 reps, half held out). It is informative whichever explanation is true. It can go live in about 5 working days with no engineering, **assuming a daily CRM export and free slots inside 48h.** **Day 1:** check the CRM's reminder rules; if reminders only fire for demos within 48h, fix that first. **Day 3:** check slot capacity in each shift; this is the go/no-go gate. **Rejected:** *48h booking rule* (easy to game, changes the reps' core task, hard to measure) · *WhatsApp reminders* (nobody has checked whether late demos get fewer; template approval puts the 2-week launch at risk) · *Risk score* (nothing to rank beyond the 48h flag) · *AI rebooking agent* (more than 2 weeks, needs CRM/calendar integration, highest brand risk).

## 5. The build
`rescue_sheet.html` is one offline page with nothing to install; the data never leaves the browser. It loads the CRM export, flags late demos, shows each deadline in the parent's local time, marks each row MOVE (at least 3h left) or CONFIRM, splits the arms and sorts by deadline per rep, with a call script and a one-click outcome log. A **first-seen register** fixes each demo's arm and MOVE-eligibility the first time it is listed, so a demo moved earlier in the CRM stays in its arm. Summary and Measurement tabs give the % worked and the verdict. Case data, 15 Jul 09:00: 92 flagged (43 MOVE). 72 automated checks pass; a pandas re-implementation agrees. Runbook (who exports, merges logs, pulls results): `prototype/README.md`.

## 6. Adoption risk
**Reps don't work the rows, or work them after the deadline.** It is an extra task outside their targets with a window of hours, and low completion would make a real effect look like none. **Mitigations:** about 1 row per rep per day, rows sorted by deadline, a supplied script, a one-dropdown log, and completion visible to the shift lead mid-shift. **Guardrail:** at least 80% of rescue rows worked before the deadline; below that, fix adoption before reading any result.

## 7. Measurement
The pilot is randomised from day one, with the readout at week 4 (~300 demos per arm). **Primary:** J/S of the rescue arm minus the control arm, intent-to-treat, with a 95% CI, in the **MOVE-eligible stratum** (deadline at least 3h away when first listed); all listed late demos are the secondary readout. 300 per arm gives ~80% power only for a ~11 pp effect. **Decision rule, set in advance** (minimum worthwhile effect +3 pp): **Scale** if the lower end of the CI is above 0. **Stop** only if the upper end of the CI is below +3 pp. **Otherwise extend.** **Guardrails:** C/J and V/C of rescue-arm joiners do not fall below control. **Displacement:** the share of new bookings more than 48h out stays at or below 39.8%.

## 8. Baseline (registered before go-live, Jun–Jul 2026)
| Late share of scheduled demos | **J/S, late (primary)** | J/S ≤48h / all | V/S, late | C/J, V/C of late joiners | A/A check: rescue − control |
|---|---|---|---|---|---|
| 39.8% | **46.9%** | 74.9% / 63.8% | 9.6% | 87.9% / 23.2% | −1.0 pp (CI −6.4 to +4.5) |
