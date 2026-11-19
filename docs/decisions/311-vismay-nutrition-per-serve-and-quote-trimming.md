# 311 · Per-serve nutrition fields, and quotes trimmed to their verbatim opening

**Status:** accepted (20 Nov 2026) · **Owner:** Vismay · **Requirements:** F1, F5, D1, A3, demo #2 · **Follows:**
decision 310

## Context
After decision 310 every labelling requirement except nutrition could be quoted and decided live. Two things still
stopped any label from clearing:

1. **The request could not say what 5(3)(b) asks for.** FSS-LD-2020 5(3)(b) requires the "per serve percentage (%)
   contribution to Recommended Dietary Allowance" (on 2000 kcal, 67 g fat, 22 g saturated fat, 2 g trans fat, 50 g
   added sugar, 2000 mg sodium) and 5(3)(b)(iv) "the number of servings in the package". `NutritionPanel` had no field
   for either, so a complete panel was always `cannot_determine` or `unmet`, and `nutrition.other` rejects percentages.
2. **The model's quotes from long clauses were rarely verbatim.** It copied the 5(3)(b) nutrient list and dropped
   "(other than naturally occurring trans fat)" from the middle, or joined two pieces that are not contiguous. The
   whole quote was dropped, so the finding was `cannot_determine`. It also cited `Schedule I, item 14` for the
   retrieved `Schedule I, item 14~substituted`, and the verifier read `veg_status: veg` as a product property.

## Decision
- **Contract (additive):** `NutritionPanel.servings_per_pack` (number) and `NutritionPanel.rda_percent_per_serve`
  (object of number, keyed `energy`, `total_fat`, `saturated_fat`, `trans_fat`, `added_sugars`, `sodium`: the
  nutrients 5(3)(b) states an RDA reference for). Both optional, both "as printed". The gate checks ranges (servings
  > 0, ≤ 10 000; each percentage 0–1 000) and keys; `docs/data-contract.md` and the published schema list them.
- **Grounding fallback:** when a quote is not verbatim as a whole, keep its parts in order up to the first one that is
  not in the passage, and of that part only the longest opening that is verbatim and ends at `;`, `.` or `:`. The
  rest is dropped. A part with no verbatim opening (invented or out of order) still rejects the whole quote, as the
  2026-11-06 incident decided, and a quote that drops a "not" has no verbatim opening to keep. The kept text is always
  the passage's own contiguous text, and the verifier still judges whether it supports the finding.
- A citation to `<id>` also resolves to the retrieved `<id>~substituted` (in-force) wording; never to superseded text.
- The verifier's facts say which mark is printed, as the researcher's do (decision 310).

## Options rejected
- Dropping nutrition from the checklist: it is in the corpus and mandatory, so that would be faking a clear.
- Accepting any quote whose words all appear somewhere in the passage: a dropped "not" would pass.
- Computing the per-serve percentages in the service: the requirement is that the label *prints* them; the request
  has to say what is printed.

## Consequences
- First live `clear-for-print` (run `2fc8f6dd192d45e4ae051ae175d24335`, R9, all 9 requirements met with verified
  citations) and first live `revise-and-recheck` (run `4265812b17874886a5454bcaff8c9c67`, R7, licence unmet citing
  5(7)), on a complete bran-flakes label and the same label without its licence number.
- A label that omits the per-serve percentages or the servings still escalates: correct, since 5(3)(b) requires them.
- The eval scenarios predate these fields, so their clear and revise cases still escalate on the real LLM until they
  carry them; not re-measured today (free-tier budget). The CI eval gate uses fakes and is unchanged.
