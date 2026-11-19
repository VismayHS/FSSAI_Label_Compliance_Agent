# 309 · Protein RDA: adopt no value; a claim stated in % of RDA escalates to regulatory review

**Status:** accepted (19 Nov 2026) · **Owner:** Vismay, recording the decision of Nishkal and Vihaan, whose open
question it was · **Requirements:** F4, F5, F7, demo #10

## Context
The §4.1 case asks whether "source of protein" is permitted given the declared protein. The condition is
FSS-AC-2018 Schedule I, item 11: *"11. Protein Source 10% of RDA per 100 g for solids 5% of RDA per 100 ml for
liquids or 5% of RDA per 100 kcal"* (`docs/eval1/section-4.1-passages.md`, P1). It is a share of the RDA, and
neither regulation states a protein RDA: both define RDA by reference to ICMR (P5), which is not in the corpus.

Nishkal proposed on 17 Nov (PR #20) to keep the current answer, and listed what a number would need:
- ICMR–NIN's 2020 summary (Table 2a) gives protein as 0.83 g/kg/day across several reference groups. Turning that
  into one gram threshold for a product claim means choosing a reference group, which is a regulatory judgement.
- The indexed Claims compendium is Version II (2021). The 13 Dec 2022 amendment to Schedule I item 11 adds a
  per-serving basis, so a numeric answer would also need the corpus updated and the test values revalidated.

Vihaan's test values (`docs/eval1/section-4.1-test-values.md`) already give `cannot_determine` →
`regulatory-review` as the reference answer while no RDA is adopted, and give the outcome for any adopted value R.

## Options
| Option | For | Against |
|---|---|---|
| 1. Configure an ICMR value as a cited external reference | Demo #10 shows a met/unmet comparison | A person must pick a reference group, which is the judgement the system must not make; the answer would rest on a number that is not FSSAI text; the corpus predates the 2022 amendment |
| **2. Adopt no value; escalate whenever the outcome depends on the RDA** | Every statement stays grounded in retrieved FSSAI text; matches the glossary ("stating a provision that does not exist is more serious than declining to answer") and F7; no code or eval change | Demo #10 shows an escalation, not a comparison |
| 3. Option 1, but escalate within ±20 % of the threshold | Escalates the doubtful cases | Has every drawback of option 1 for the cases it does answer |

## Decision
Option 2. No protein RDA is adopted. For the §4.1 case and every claim whose condition is a share of the RDA:
- the finding is `cannot_determine`, citing the condition (FSS-AC-2018 Schedule I item 11), and the nutrition
  declaration is checked under FSS-LD-2020 5(3)(b), so both regulations are cited;
- the route is `regulatory-review`, with the reason that the RDA value is not in the corpus.

`RESEARCHER_RDA_GUARD=1` (the default) stays on, and the verifier keeps escalating a met/unmet finding against an
RDA condition.

## Consequences
- Demo #10 presents this as the correct answer: the system finds the condition in the other regulation, cites
  both, and declines to compare rather than invent a threshold (F7).
- The system's ability to compare a declared value with a condition is shown where the condition is stated in
  grams: the `fibre-source-pass` / `fibre-source-fail` scenarios route `clear-for-print` / `revise-and-recheck`.
- The five `rda-pending` scenarios keep their current expected answers; no eval rerun is needed.
- Revisiting this means the three steps in the test values page ("What changes when the team adopts an RDA"),
  after a person has chosen the reference group and the corpus has the 2022 amendment.
