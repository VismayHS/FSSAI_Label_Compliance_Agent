# §4.1 test values: "source of protein"

Owner: Vihaan (V1.3, Evaluation 1) · Passages: Nishkal, [`section-4.1-passages.md`](section-4.1-passages.md) (P1–P12) ·
Eval set: `packages/eval/scenarios.jsonl` (the `section-4.1` tag) · Routing rules: [decision 201](../decisions/201-vihaan-routing-rules.md)

> *"The label carries the claim 'source of protein'. Is the claim permitted, given the protein content declared on
> the nutrition panel?"* (spec §4.1)

These are the reference answers for demo item 10 and for the `section-4.1` eval scenarios. Every regulation quote
is copied from the corpus as the indexer extracts it, and `packages/eval/tools/check_scenarios.py` checks each one against
the index.

## The condition, and why no number appears in it

FSS-AC-2018 Schedule I, item 11 (P1, substituted text, in force):

> "11. Protein Source 10% of RDA per 100 g for solids 5% of RDA per 100 ml for liquids or 5% of RDA per 100 kcal"

FSS-AC-2018 5(3) (P2) makes it binding: *"When a nutrient content or any synonymous claim is made for the nutrients
indicated in schedule -I, itshall be made in accordance with the conditions specified in Schedule I"*. The declared
value comes from the Labelling regulation, FSS-LD-2020 5(3)(b)(ii) (P6): *"(ii) the amounts of (A) Protein (g);"*.

The condition is a share of the **RDA**, and **no protein RDA value is in the corpus**: both regulations defer to
ICMR (P5). Until the team adopts one (Nishkal's open question; the options are in the passages page), the threshold
is written symbolically:

    breakfast cereals are solids  →  condition: protein_g ≥ 0.10 × RDA        (per 100 g)
                                     or         protein per 100 kcal ≥ 0.05 × RDA

So each case below gives two expected answers:

1. **Now (no RDA adopted; the reference answer for the eval set):** the finding is `cannot_determine` and the route
   is `regulatory-review`. The researcher's RDA guard (`RESEARCHER_RDA_GUARD=1`) produces that, and if a finding
   says `met` or `unmet` against this condition anyway, the verifier escalates it ("the condition is a share of the
   RDA, and the RDA value is not in the cited text"). This is the system knowing when *not* to answer (F7).
2. **Once an RDA value R is adopted** (read from ICMR by a person, recorded in a decision record, cited as an
   external reference): the outcome follows from plain arithmetic on the condition above. For each case we give the
   range of R for which each basis is met, so the expected answer can be read off for any R without recomputing.

The ranges are exact: per 100 g the condition is met iff R ≤ protein_g / 0.10; per 100 kcal it is met iff
R ≤ (protein_g × 100 / energy_kcal) / 0.05.

## Case A: pass candidate (clearly above)

Scenario `s41-protein-clearly-above`. 14 g protein per 100 g (the `protein-claim-met` load payload's value), 383 kcal
per 100 g, so 3.66 g per 100 kcal.

```json
{
  "schema_version": "1.0",
  "declared_category": "breakfast-cereals",
  "package": {
    "net_quantity": 500.0,
    "net_quantity_unit": "g",
    "principal_display_panel_cm2": 180.0,
    "total_surface_area_cm2": 900.0,
    "pack_type": "single"
  },
  "label": {
    "product_name": "Protein muesli",
    "brand_name": "Kheti Foods",
    "front_of_pack_text": "Source of protein.",
    "claims": [
      "Source of protein"
    ],
    "ingredients": "Rolled oats (40%), soy crisps (20%), whole wheat flakes, almonds, raisins, sugar",
    "allergen_statement": "Contains: oats, wheat (gluten), soy, almonds.",
    "veg_status": "veg",
    "fssai_licence_number": "10019022000123",
    "manufacturer_name_address": "Manufactured by: Kheti Foods Pvt Ltd, Plot 12, MIDC, Pune 411019",
    "date_marking": "Mfg: 08/2026  Use by: 07/2027",
    "batch_or_lot": "Batch No. KF2608A"
  },
  "nutrition": {
    "basis": "per_100g",
    "serving_size": 30.0,
    "serving_unit": "g",
    "energy_kcal": 383.0,
    "protein_g": 14.0,
    "carbohydrate_g": 66.0,
    "total_sugars_g": 11.0,
    "total_fat_g": 7.0
  }
}
```

| | Per 100 g | Per 100 kcal |
|---|---|---|
| Declared | 14 g | 3.66 g |
| Met iff | R ≤ 140 g | R ≤ 73.1 g |

- **Now:** `regulatory-review`. Finding `CLM-PROTEIN-SOURCE` = `cannot_determine`, explanation "the condition is 10 %
  of RDA per 100 g and the RDA value is not in the corpus". `LBL-NUTRITION` = `met` (protein is declared per 100 g).
- **With R adopted:** for R ≤ 73.1 g both bases are met, so the finding is `met` and the label routes on its other
  findings (here all present: `clear-for-print`, with the not-an-approval notice). For 73.1 < R ≤ 140 the two bases
  disagree, which gives `regulatory-review` (see case D).
- **Citations (both regulations):** FSS-AC-2018 Schedule I, item 11, *"11. Protein Source 10% of RDA per 100 g for
  solids"*; FSS-AC-2018 5(3), *"itshall be made in accordance with the conditions specified in Schedule I"* (the
  text layer's own spacing, kept so the quote matches the corpus exactly); FSS-LD-2020 5(3)(b)(ii), *"(ii) the
  amounts of (A) Protein (g);"*.

## Case B: fail candidate (clearly below)

Scenario `s41-protein-clearly-below`. 2.5 g protein per 100 g (the `protein-claim-low` load payload's value), 375.5 kcal,
so 0.67 g per 100 kcal.

```json
{
  "schema_version": "1.0",
  "declared_category": "breakfast-cereals",
  "package": {
    "net_quantity": 500.0,
    "net_quantity_unit": "g",
    "principal_display_panel_cm2": 180.0,
    "total_surface_area_cm2": 900.0,
    "pack_type": "single"
  },
  "label": {
    "product_name": "Puffed rice crisps",
    "brand_name": "Kheti Foods",
    "front_of_pack_text": "Source of protein.",
    "claims": [
      "Source of protein"
    ],
    "ingredients": "Puffed rice (80%), wheat flour (10%), sugar, iodised salt",
    "allergen_statement": "Contains: wheat (gluten).",
    "veg_status": "veg",
    "fssai_licence_number": "10019022000123",
    "manufacturer_name_address": "Manufactured by: Kheti Foods Pvt Ltd, Plot 12, MIDC, Pune 411019",
    "date_marking": "Mfg: 08/2026  Use by: 07/2027",
    "batch_or_lot": "Batch No. KF2608A"
  },
  "nutrition": {
    "basis": "per_100g",
    "serving_size": 30.0,
    "serving_unit": "g",
    "energy_kcal": 375.5,
    "protein_g": 2.5,
    "carbohydrate_g": 88.0,
    "total_sugars_g": 6.0,
    "total_fat_g": 1.5
  }
}
```

| | Per 100 g | Per 100 kcal |
|---|---|---|
| Declared | 2.5 g | 0.67 g |
| Met iff | R ≤ 25 g | R ≤ 13.3 g |

- **Now:** `regulatory-review`, `CLM-PROTEIN-SOURCE` = `cannot_determine`.
- **With R adopted:** for R > 25 g neither basis is met, so the finding is `unmet` and the route is `revise-and-recheck`
  ("remove the claim or reformulate"), citing the same three passages. (For 13.3 < R ≤ 25 the bases disagree:
  `regulatory-review`.)

## Case C: boundary (exactly at the condition)

There is no fixed number until R is known, so this case is a template: **protein_g = 0.10 × R** per 100 g.

- **Expected, whatever R is:** `regulatory-review`, finding `cannot_determine`. A declared value exactly at a
  minimum is met on paper. But FSS-LD-2020 5(3)(d) (P9) allows declared nutrients *"the tolerance of ± 20 percent of
  the value for that nutrient declared on the label"*, so the product's real content may lie on either side of the
  line. The verifier escalates whenever declared × (1 ± 20 %) spans the threshold (`VERIFIER_TOLERANCE_PCT=20`). It
  does **not** use the tolerance to stretch a value over the line (P9's own note).
- The same rule on a condition the corpus states in grams is scenario `fat-low-boundary`: "Low fat" with exactly 3 g
  fat per 100 g against *"2. Fat Low Not more than 3 g of fat per 100 g for solids"*, giving `regulatory-review`.

## Case D: the basis differs

Scenario `s41-protein-basis-differs`. 9 g protein per 100 g, but an energy-dense granola at 446 kcal per 100 g, so
2.02 g per 100 kcal. Schedule I offers two bases joined by "or".

```json
{
  "schema_version": "1.0",
  "declared_category": "breakfast-cereals",
  "package": {
    "net_quantity": 500.0,
    "net_quantity_unit": "g",
    "principal_display_panel_cm2": 180.0,
    "total_surface_area_cm2": 900.0,
    "pack_type": "single"
  },
  "label": {
    "product_name": "Nut and seed granola",
    "brand_name": "Kheti Foods",
    "front_of_pack_text": "Source of protein.",
    "claims": [
      "Source of protein"
    ],
    "ingredients": "Rolled oats (40%), almonds (15%), pumpkin seeds (10%), wheat flakes, honey, sunflower oil",
    "allergen_statement": "Contains: oats, wheat (gluten), almonds.",
    "veg_status": "veg",
    "fssai_licence_number": "10019022000123",
    "manufacturer_name_address": "Manufactured by: Kheti Foods Pvt Ltd, Plot 12, MIDC, Pune 411019",
    "date_marking": "Mfg: 08/2026  Use by: 07/2027",
    "batch_or_lot": "Batch No. KF2608A"
  },
  "nutrition": {
    "basis": "per_100g",
    "serving_size": 30.0,
    "serving_unit": "g",
    "energy_kcal": 446.0,
    "protein_g": 9.0,
    "carbohydrate_g": 62.0,
    "total_sugars_g": 12.0,
    "total_fat_g": 18.0
  }
}
```

| | Per 100 g | Per 100 kcal |
|---|---|---|
| Declared | 9 g | 2.02 g |
| Met iff | R ≤ 90 g | R ≤ 40.4 g |

- **Now:** `regulatory-review`, `cannot_determine`.
- **With R adopted:** for 40.4 < R ≤ 90 g the per-100 g basis is met and the per-100 kcal basis is not. The row does
  not say which basis governs, or whether meeting either is enough (Nishkal's interpretation note), so this is
  `regulatory-review` with "the bases disagree", not a guess. The verifier's numeric check reports exactly this
  (`bases_disagree`). For R ≤ 40.4 both are met; for R > 90 neither is.
- The same shape with a gram condition is scenario `fibre-basis-differs`. *"Source Product contains at least 3 g of
  fibre per 100 g or 1.5 g of fibre per 100 ml or 1.5 g of fibre per 100kcal"*: 4 g per 100 g meets the first, while
  1.0 g per 100 kcal fails the third, giving `regulatory-review`.

## Related cases in the eval set

| Scenario | What it adds | Expected |
|---|---|---|
| `s41-protein-synonym` | "Contains protein": a Schedule II synonym of "Source" (P3). The phrase is in neither regulation, so literal matching finds nothing. | `regulatory-review` (RDA) |
| `s41-protein-high` | "High protein": Schedule I item 11 Rich / High, 20 % of RDA | `regulatory-review` (RDA) |
| `fibre-source-pass` / `-fail` | The pass/fail pair on a condition stated in grams: 9 g and 1.5 g fibre against 3 g per 100 g | `clear-for-print` / `revise-and-recheck` |
| `out-of-scope-supplement` | A protein powder: claims for health supplements are governed elsewhere (Schedule I, Note 1; P11) | `regulatory-review` |
| `small-pack-with-claim` | A ≤ 100 cm² pack (8(1), P8) carrying a claim (5(3)(c) proviso, P7) | `regulatory-review` |

## What changes when the team adopts an RDA

1. A decision record states the ICMR edition, table and value R, and is marked as an external reference, not FSSAI
   text.
2. The researcher's RDA guard is turned off for that nutrient, and the value reaches the agents as a cited
   reference.
3. In `packages/eval/scenarios.jsonl`, the scenarios tagged `rda-pending` get their "with R adopted" answers from the tables
   above (one edit per scenario), and the before/after eval shows the change.
