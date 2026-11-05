# 2026-11-06: grounding dropped correct quotes, so labels that should clear or be revised all escalated

- **Author:** Vismay · **Severity:** demo #2 could only ever show `regulatory-review`; route accuracy on the
  clear/revise scenarios was 0 on the real LLM
- **Component:** `packages/agents/fssai_agents/grounding.py` (the researcher's citation grounding, A3)

## What happened

The researcher 1.0.0 vs 1.1.0 comparison (8 scenarios per variant, real Groq) routed every scenario that should end
`clear-for-print` or `revise-and-recheck` to `regulatory-review`. The findings themselves were mostly right:
`missing-allergen` had its allergen finding `unmet`, as expected, and the verifier marked every check supported.

## How it was noticed

The eval rows had the right finding statuses but the wrong route. One real run of `missing-allergen`, with the routing
reason printed, said `[R1] ... LBL-FSSAI-LICENCE: no verbatim citation survived grounding; LBL-MANUFACTURER: ...`.

## Cause

Two ways the model quotes a real passage that the old check (normalised substring) refused:

1. **Words the PDF text extraction split.** The indexed passage reads *"shall be dis played on the label"*,
   *"Every pac kaged food meant for non -retail sale"*. The model quotes *"displayed"*, *"packaged"*,
   *"non-retail"*. The old check collapsed whitespace but did not remove it, so the quote never matched.
2. **Quotes shortened with "..."** (already seen on 27 Oct, smoke run `247f11fb07eb46e7963bf7decf500a08`):
   *"Nutritional Information per 100g or 100ml ... shall be given on the label"* is not one span.

A finding whose only quote is dropped becomes `cannot_determine`, which rule R1/R5 sends to a person. The system
failed safe (no label was cleared wrongly) but it could never clear one.

## Fix

- Matching now ignores whitespace entirely, and maps the match back to the passage's own characters, so the stored
  quote is still the exact passage text (`"dis played"` included). The characters must still match one for one, so
  different words are still rejected (`test_ignoring_whitespace_still_rejects_different_words`).
- A quote with `...`, `…`, `. . .` or `[...]` is kept only if every part is in the passage **in order**; each part
  long enough to stand alone is stored as its own verbatim citation. One invented or out-of-order part drops the whole
  quote.
- Tests use the real passages and quotes from these runs (`packages/agents/tests/test_researcher.py`).

## Lesson

"Verbatim" has to mean verbatim against the text we indexed, not against the PDF as a person reads it. When a strict
check fails safe, it looks like caution in the logs; the eval's per-route accuracy is what showed it was a bug. Keep the
routing reason in eval rows, so the next one is found from the results file instead of a re-run.
