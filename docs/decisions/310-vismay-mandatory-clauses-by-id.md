# 310 · Mandatory declarations: read their clauses by id, and resolve citations the way the index stores them

**Status:** accepted (20 Nov 2026) · **Owner:** Vismay, on Namith's researcher (`packages/agents`) · **Requirements:**
F4, F5, A1, A3, demo #2 · **Changes:** decision 102 (broad sweep queries), decision 103 (default prompt pair)

## Context
On the real stack no label had ever been routed `clear-for-print` or `revise-and-recheck`: the last 100 runs (5 to 19
Nov) were all `regulatory-review`, and so were the eval's clear and revise scenarios. Live runs of a label that has
every declaration (`fibre-source-pass`) showed three causes, none of them in the routing rules:

1. **The sweep never retrieved four clauses.** Decision 102 grouped the labelling requirements into five broad
   searches to save tool calls. Against the real index, "allergen declaration and vegetarian non-vegetarian logo"
   returned 5(4)(a)-(d) and 5(14)(vii) (soybeans) but not 5(14) itself; "list of ingredients and net quantity" returned
   parts of 5(2) about compound ingredients but not the rule that a list is required; the licence and manufacturer
   query returned 10(1), the non-retail rule, not 5(6). With nothing to quote, those findings were `cannot_determine`.
2. **Correct quotes were dropped.** The index stores a long clause whole as `<id>#all` (and in parts). The model saw
   `[FSS-LD-2020:5(14)#all]` and cited `FSS-LD-2020:5(14)`; grounding looked that id up, found nothing and dropped a
   verbatim quote.
3. **Findings filed under the model's own id were reported missing.** With the 1.0.0 draft prompt the model is never
   shown the researched ids, so it wrote `LBL-BATCH-LOT`, `LBL-NUTRITION-PANEL`, `LBL-NETQTY`; the coverage check then
   added "LBL-BATCH: searched, but no finding was drafted", which escalates.

## Options
| Option | For | Against |
|---|---|---|
| Better wording for the five broad searches | No more tool calls | Tried on the index: still misses 5(14) or 5(6) depending on wording; retrieval decides coverage of a fixed checklist |
| One search per requirement | Simple | Same tool cost as a lookup, and still not certain to return the clause |
| **Read each mandatory declaration's clause by id (`clause_lookup`)** | Certain: the clause is always in the dossier; costs no embedding | Hard-codes which clause states each requirement; 8 tool calls instead of 5, so the bounds rise |

## Decision
- The sweep looks up FSS-LD-2020 5(3)(b) nutrition, 5(14) allergen, 5(4)(b) or (a) veg / non-veg mark (from
  `veg_status`), 5(2) ingredients, 5(10)(a) date marking, 5(9) batch, 5(7) licence and 5(6) name and address. The
  small-pack exemption is still searched for. Every clause id was checked against the built index.
- **Net quantity is no longer researched.** 5(8) says only that its declaration "shall be as provided in Legal
  Metrology Act, 2009", which is not in the corpus, so no finding about it can be grounded in FSSAI text; the data
  contract already requires a positive `net_quantity` at the gate.
- A citation to `<id>` resolves to a retrieved `<id>#...` passage of the same clause. The quote must still be verbatim
  in it; any other id or a paraphrase is still dropped.
- A drafted id maps onto the researched id it names (same prefix, token overlap ≥ 0.5, as the eval's matcher does).
- The request facts say which mark is printed (`veg_or_non_veg_mark_printed_on_pack`), because the data contract
  defines `veg_status` as the mark on the pack and the model read `veg` as a product property.
- Bounds: `RUN_MAX_STEPS` 25 → 30, `RUN_MAX_TOOL_CALLS` 15 → 18. `test_step_budget.py` measured 18 steps and 9 tool
  calls for a verified run and exactly 30 / 13 for the worst case (three research attempts, busy model).
- Default prompt pair 1.0.0 → 1.1.0. Decision 103 preferred 1.0.0 on runs where causes 1 and 2 made nearly every
  labelling finding `cannot_determine`; 1.1.0 is the pair that lists the researched ids for the draft.

## Consequences
- Live, `fibre-source-pass` went from 5 of 9 labelling findings `met` to 8 of 9, each quoting its clause, and a copy
  with no licence number returns `LBL-FSSAI-LICENCE: unmet` with 5(7) quoted.
- These runs still route `regulatory-review`, correctly: 5(3)(b) also requires per-serve percentage contribution to
  the RDA, and `LabelCheckRequest` has no field for it, so the nutrition finding is `cannot_determine`. Clearing a
  label needs an additive contract field for those values; that is the next change, not this one.
- Not re-measured with the eval set (free-tier token budget on submission day). The CI eval gate uses fakes for the
  researcher, so its baseline is unchanged.
- The safety checks are unchanged: every quote must be verbatim in a passage retrieved in this run, and the verifier
  and router are untouched, so a finding still reaches `clear-for-print` only through them.
