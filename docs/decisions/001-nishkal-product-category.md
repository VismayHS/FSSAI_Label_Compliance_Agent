# 001: Product category: breakfast cereals

- **Owner:** Nishkal · **Status:** Proposed. The team confirms it in the group chat; Vismay records the confirmation in the project plan.
- **Requirement:** spec §3 "Select one product category and stay within it"; F7 (out-of-corpus categories escalate)

## Context

The system must stay within one product category, and anything outside it must escalate (F7). The
category also decides which provisions the evaluation set exercises. The demo case (§4.1) is a "source
of protein" claim, so the category should be one where protein claims are common and where the claim
condition (FSS-AC-2018 Schedule I, item 11) applies without detours into other regulations.

## Options

| Option | For | Against |
|---|---|---|
| **Breakfast cereals** (flakes, muesli, granola, oats) | Protein, fibre, sugar and "whole grain" claims are common on Indian cereal packs, so §4.1 is a natural case. They are solids, so one clear basis (per 100 g; FSS-AC-2018 Sch. I "for solids"). Allergens (gluten: wheat, oats, barley) exercise FSS-LD-2020 5(14). Schedule II 1(8)–(9) of the Labelling regulation names "breakfast cereals" and "flakes and ready to eat dry breakfast cereals" for the trehalose and dextrin declarations, so there are in-category mandatory declarations to test. | Few category-specific compositional standards in our two regulations, so fewer "name of food" traps. |
| Protein bars / snack bars | Protein claims everywhere; "high protein" (Sch. I item 11 Rich/High) as well as "source" | Many bars are marketed close to health supplements, whose nutrient content claims are governed by another regulation (Sch. I Note 1). The boundary is hard to state in a data contract, and most requests would escalate. |
| Dairy-based beverages | Protein claims common | Liquids switch the basis to per 100 ml. Milk products bring in standards outside our corpus (FSS Food Product Standards), so many findings would be "outside corpus". |

## Decision

**Breakfast cereals** (`CORPUS_CATEGORIES=breakfast-cereals`). Requests declaring another category are
out of scope and escalate with the reason "category outside corpus" (F7). Protein powders and anything
sold as a health supplement are explicitly out, because FSS-AC-2018 Schedule I, Note 1 sends their claims
to a regulation we do not hold (see `docs/eval1/section-4.1-passages.md`, P11).

## Consequences

- Vihaan's gate lists `breakfast-cereals` as the only permitted `declared_category` value besides the
  explicit "unsupported" handling. The eval set's in-scope scenarios are cereals.
- Namith's classifier cross-checks the declared category against the label text (a "cereal" with
  "whey protein isolate" first in the ingredients and supplement wording is suspicious, so it escalates).
- Load-test payloads (`infra/loadtest/payloads/`) are cereals.
- `packages/contracts/fssai_contracts/conformance.sample_request()` reads the category from `CORPUS_CATEGORIES`,
  so the conformance tests keep working with the new value.
