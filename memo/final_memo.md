# BrightChamps: Late-Demo Rescue

**Memo, one page** · Data: 5,000 leads, 1 Jun to 31 Jul 2026 (case export) · ₹60,000 revenue per customer and ₹900 per lead, as given in the case

## 1. The leak
**40% of demos are booked more than 48h after the lead arrives, and those parents show up far less often.** Of 3,229 scheduled demos, 1,285 (39.8%) fall more than 48h after `created_at`. They are joined **46.9%** of the time, against **74.9%** for demos within 48h (−28.0 pp, 95% CI −31.3 to −24.7). They account for 58% of all no-shows. The gap appears in every source, country, shift, rep and week, and still holds after adjusting for all measured variables (OR 0.27). Once a late-booked parent joins, they complete and convert at least as well as everyone else (C/J 87.9%, V/C 23.2%), so the loss happens at the join step. **This is a correlation, not proven cause:** parents who are less keen may simply choose later slots.

## 2. Financial impact
**Planning case: ≈ ₹7.8 lakh/month in revenue. Ceiling: ≈ ₹17.7 lakh/month.**
`1,285 late demos × 24.65 pp (low end of CI) × 50% causal share × 16.4% customers per joiner ≈ 26 customers × ₹60,000 = ₹15.6 lakh / 2 months`
The ceiling assumes the whole 28 pp gap closes: 360 extra joins → 59 customers → ₹35.4 lakh over 2 months. The 50% causal share is a judgment call, not a measurement (25% gives ₹3.9 lakh/month). These figures are revenue, not profit, and are not a proven loss. The ₹900 CPL is already spent, so it is not deducted.

## 3. The lever
**A daily Late-Demo Rescue list.** Each shift gets a list of upcoming demos booked more than 48h after the lead arrived. The owning rep calls or WhatsApps the parent and offers a slot before the **rescue deadline, `created_at + 48h`**. If the parent won't move, the rep confirms the current slot live. Leads with an odd ID go to reps; leads with an even ID are held back as an untouched control.

## 4. Why this lever
It works on the exact population and boundary where the gap sits. It goes live in about 5 working days with no engineering (an existing export plus a sheet). The load is about 1 call per rep per day (≈21 late demos a day across 12 reps, half held back). The holdout makes it measurable from day one, and it is useful whichever explanation is true: moving the demo tests the wait, and the confirmation call reveals the parent's intent. **Rejected:** *48h booking rule*: easy to game ("parent asked"), changes the reps' core task, and hard to measure fairly. *WhatsApp reminders*: only helps if late demos currently get fewer reminders, which nobody has checked, and template approval puts the 2-week launch at risk. *Risk score*: no signal beyond the 48h flag, and every row can already be worked. *AI rebooking agent*: needs more than 2 weeks, needs CRM/calendar integration, and carries the highest brand risk.

## 5. The build
`prototype/rescue_sheet.html` is a single offline page with nothing to install; the data never leaves the browser. It loads the CRM export, flags demos booked more than 48h out, and computes each deadline in the parent's local time. Each row is marked MOVE (the deadline is still open) or CONFIRM (it has passed). Rows are split odd/even into rescue and control, sorted by deadline, and filtered per rep. The page includes the call script and a one-click outcome log. Summary and Measurement tabs give the shift lead the % of rows worked and the week-4 verdict. On the case data as of 15 Jul 09:00 it flags 92 demos (45 MOVE, 47 CONFIRM). 61 automated checks pass, and an independent pandas version agrees on 23,836 flagged rows.

## 6. Adoption risk
**Reps don't work the rows, or work them after the deadline.** It is an extra task outside their targets, and the rescue window is hours long. Low completion would make a real effect look like no effect. Mitigations: small load, rows sorted by deadline, a supplied script, a one-dropdown outcome log, and completion visible to the shift lead mid-shift. **Guardrail:** at least 80% of rescue rows worked before the deadline, checked daily.

## 7. Measurement
4-week pilot, about 300 demos per arm (enough to detect an ~11 pp lift). **Primary:** join rate (J/S) of the rescue arm minus the control arm, intent-to-treat, with a 95% CI. **Diagnostic:** J/S by outcome (moved / confirmed / no answer). **Guardrails:** C/J and V/C of rescue-arm joiners do not fall below control. **Decision rule, set in advance:** *Scale* if the CI excludes zero and completion is ≥80%. *Stop or pivot* if the CI includes zero and completion is ≥80%. *Inconclusive, fix adoption first* if completion is below 80%. The randomised holdout is what turns the correlation into a causal test.

## 8. Baseline (registered before go-live)
| Metric (Jun–Jul 2026) | Baseline |
|---|---|
| Share of scheduled demos booked >48h out | 39.8% |
| **J/S, demos >48h (primary)** | **46.9%** |
| J/S, demos ≤48h / all scheduled | 74.9% / 63.8% |
| V/S, demos >48h | 9.6% |
| C/J, V/C of late joiners (guardrails) | 87.9% / 23.2% |
| Rescue vs control arms on historical data (A/A check) | −1.0 pp (CI −6.4 to +4.5) |

The target to beat for the planning case is +12.3 pp J/S on late demos (46.9% → about 59%).
