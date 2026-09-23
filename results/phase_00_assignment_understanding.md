# Phase 0 — Assignment Understanding

Source: `BrightChamps_FDA_Take_Home_Case_CANDIDATE.pdf` (the only source used). No dataset analysis done and no solution proposed yet.

## 1. The business problem
BrightChamps has a sales funnel: a lead comes in, a demo gets scheduled, the parent joins the demo, the demo is completed, and the lead converts to a paying customer. Leads are lost at each step, and every lost lead costs money. We have to find where the funnel loses the most money, put a rupee figure on it, and propose a fix that can go live quickly.

The dataset has 5,000 anonymised leads covering two months. Its fields are lead id, lead source, geography, parent timezone, created timestamp, demo scheduled timestamp, rep assigned, rep shift, number of follow-up attempts, demo joined (Y/N), demo completed (Y/N) and converted (Y/N).

## 2. The four deliverables
1. **The Leak**: where the funnel loses the most money, in ₹ per month.
2. **The Lever**: one intervention to fix it, plus the options we considered and rejected.
3. **The Build**: a working prototype of one component.
4. **The Memo**: a one-page summary.

## 3. The Leak
The leak is the single biggest place in the funnel where money is lost. We must state it as **₹ per month** and **show our working**. The PDF says they "care more about how you sized it than about the exact figure." So the method and assumptions count for more than the final number.

## 4. The Lever
The lever is **one** intervention that:
- could be **live within two weeks**
- needs **no engineering sprint**

We have to explain why we chose it over the alternatives. The PDF says the **rejected options matter as much as the chosen one**, so each rejected option needs a written reason.

## 5. The Build
The build is a **working prototype of one component**. The PDF gives examples: "an agent and its prompt, a script, a sheet with automation, a scoring model, whatever fits." It **must actually run**, and it must come in a form they can **execute or watch**, i.e. a file, a repo link, or a live URL they can open **without installing anything**. The scoring also asks whether someone else could own and run it.

## 6. The Memo
The memo is **one page maximum**, sent as a **PDF**. It must cover:
- the lever
- the rupee number
- the biggest adoption risk
- how we would measure whether it worked
- the baseline we would register before starting

## 7. ₹60,000 per converted customer
Each lead that converts brings in about **₹60,000 in revenue** on average. This is a given assumption. It turns conversion counts into rupees: one lost conversion ≈ ₹60,000 of lost revenue.

## 8. ₹900 blended marketing cost per lead
Getting each lead costs about **₹900 in marketing**, averaged ("blended") across all lead sources. This is also a given assumption. It is the cost of every lead, whether or not it converts. For example, 5,000 leads ≈ ₹45 lakh of marketing spend.

## 9. Submission requirements
- Reply to the original email as a **single message** within **48 hours** of receiving it.
- Expected effort is **3–4 hours**. "A tight three-hour submission beats a sprawling ten-hour one."
- Attach the **memo as a PDF**.
- Send the **build as a file, repo link, or live URL** that opens without installing anything.
- **Do not send a deck.**
- **Name the AI tools used and what each one was used for.** Using them is expected, not a mark against you.
- **Write down any assumption** instead of asking. If something is ambiguous, make a call, note it, and carry on.

## 10. Evaluation
| Criterion | Weight |
|---|---|
| Problem framing and quantification | 25% |
| Lever selection and trade-off reasoning | 25% |
| Build actually runs and could be owned by someone else | 25% |
| Adoption and measurement thinking | 15% |
| Written clarity | 10% |

The PDF also says: "We are evaluating your judgment, not your unaided typing speed."
