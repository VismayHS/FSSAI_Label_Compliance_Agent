# §4.1 reference passages: "Is the claim 'source of protein' permitted?"

Owner: Nishkal (N1.1, Evaluation 1) · Test values: Vihaan, `docs/eval1/section-4.1-test-values.md` (V1.3)

> *"The label carries the claim 'source of protein'. Is the claim permitted, given the protein content
> declared on the nutrition panel?"* (spec §4.1)

Every quote below is copied from the corpus PDFs, not from memory:

| Code | File | Version |
|---|---|---|
| FSS-AC-2018 | `data/corpus/raw/FSS-AC-2018_compendium_2021-11-16.pdf` | Version-II (16.11.2021) |
| FSS-LD-2020 | `data/corpus/raw/FSS-LD-2020_compendium.pdf` | Version-VI (22.02.2023) |

Provenance and sha256 are in `data/corpus/manifest.json`. Quotes are the text layer as the system indexes it
(pypdf, whitespace collapsed), including the PDF's own spacing errors such as "itshall" and "schedule -I".
That way a citation the system makes can be checked against this page character for character. Page
numbers are the PDF page. "Passage id" is the id the retriever returns, so traces can be matched to this
page.

## The answer in one paragraph

A "source of protein" claim is a **nutrient content claim** (FSS-AC-2018 2(1)(l)(i)). By the substituted
regulation 5(3), it must meet the condition in **Schedule I**, item 11 (Protein / Source). That condition
is a share of the **RDA**: 10 % of RDA per 100 g for solids, 5 % per 100 ml for liquids, or 5 % per 100
kcal. The Labelling regulation is where the protein figure comes from: it requires protein (g) per 100 g
in the nutritional information (FSS-LD-2020 5(3)(b)). It never mentions Schedule I or the claim condition.
The only pointer from Labelling to Claims is about brand names (5(1)(c)). Neither regulation states an RDA
value for protein. Both define RDA by reference to ICMR's *Nutrient Requirements and Recommended Dietary
Allowances for Indians*. The comparison therefore needs a reference value from **outside the corpus**
(see "Open question" below).

## The passages

### P1: the claim condition (decisive) · FSS-AC-2018 Schedule I, item 11 · pp. 13–14

Passage id `FSS-AC-2018:Schedule I, item 11~substituted`. This is the *substituted* Schedule I, in force.
It was operationalised w.e.f. 26 Oct 2021, and food business operators had to comply by 1 Jul 2022.

> "11. Protein Source 10% of RDA per 100 g for solids 5% of RDA per 100 ml for liquids or 5% of RDA per 100 kcal Rich / High 20% of RDA per 100 g for solids 10% of RDA per 100 ml for liquids or 10% of RDA per 100 kcal"

The table's columns are: Sl. No · Nutrient/component · Claim · Conditions. The row starts on p. 13 and its
last line ("or 5% of RDA per 100 kcal") is on p. 14. The chunker keeps the row whole (decision 002). The
original Schedule I (pp. 9–11) has the same protein condition. The system indexes it as superseded
(`~superseded`) and does not cite it.

*Why it matters:* this is the provision the request never mentions and a single labelling search does
not find (spec §5). Note that **the phrase "source of protein" occurs nowhere in either regulation**
(`data/corpus/tools/grep_pdf.py "source of protein"` gives 0 matches). The table spells it as nutrient
"Protein" and claim "Source", in separate columns. A system that matches the claim text against the
regulations literally finds nothing.

### P2: claims must meet Schedule I · FSS-AC-2018 5(3) · p. 4

Passage id `FSS-AC-2018:5(3)~substituted` (substituted text, in force from the same Direction).

> "(3) When a nutrient content or any synonymous claim is made for the nutrients indicated in schedule -I, itshall be made in accordance with the conditions specified in Schedule I, provided flexibility in the wording of a nutrition claim is as per Schedule II, or the use of any other word if they are in accordance with conditions specified in Schedule I and the meaning of the claim is not altered."

*Why it matters:* this makes P1 binding for the claim. It also brings in Schedule II synonyms (P3), so
"Provides protein" and "Contains protein" are the same claim.

### P3: synonyms · FSS-AC-2018 Schedule II · p. 16 (heading on p. 15)

Passage id `FSS-AC-2018:Schedule II~substituted`.

> "SCHEDULE – II [See regulation 5(3)] Synonyms which may be used for claims defined in these regulations Free Low Reduced High Increased Source Zero, No, Without, Negligible Source Little, few (for calories), contains a small amount of, low source of, Lite, Light Lower, Lesser, fewer (for calories), More, Rich Higher, Enhanced Provides, Contains"

The text layer loses the table layout. In the PDF the synonyms of **Source** are "Provides, Contains".

### P4: what a nutrient content claim is · FSS-AC-2018 2(1)(l) · p. 2

Passage id `FSS-AC-2018:2(1)(l)`. The `get_clause` lookup also serves 2(1)(l)(i) on its own.

> "(i) “nutrient content claim” is a nutrition claim that directly or indirectly describes the level of a nutrient contained in a food. (Examples: contains or source of; high in; rich in; low in , etc.);"

### P5: RDA is defined outside both regulations · FSS-AC-2018 2(1)(n) · p. 2 · and FSS-LD-2020 2(1)(q) · p. 3

Passage ids `FSS-AC-2018:2(1)(n)` and `FSS-LD-2020:2(1)(q)`. The wording is near-identical. From FSS-AC-2018:

> "Explanations.- For the purposes of this clause , recommended dietary allowances values as provided in current Indian Council of Medical Research Nutrient Requirements and Recommended Dietary Allowances for Indians shall be applicable and if Indian recommended dietary allowances is not available for any nutrient then values provided in Codex or World Health Organization guidelines shall be applicable;"

*Why it matters:* P1 is in % of RDA, and the RDA value itself is in an ICMR document that is not in
the corpus.

### P6: the declared protein value · FSS-LD-2020 5(3)(b) · p. 10

Passage ids `FSS-LD-2020:5(3)(b)` and `FSS-LD-2020:5(3)(b)(ii)`.

> "(b) Nutritional Information per 100g or 100ml or per single consumption pack of the product and per serve percentage (%) contribution to Recommended Dietary Allowance calculated on the basis of 2000kcal energy, 67 g total fat, 22 g saturated fat, 2 g trans fat, 50 g added sugar and 2000 mg of sodium (5 g salt) requirement for average adult per day, shall be given on the label containing the following: —"

> "(ii) the amounts of (A) Protein (g);"

*Why it matters:* this is the labelling side, the value to compare with P1 (the request's
`nutrition.protein_g` on `basis: per_100g`). Note that the reference intakes listed here (2000 kcal, 67 g
fat, …) **do not include protein**, so they cannot supply the protein RDA either.

### P7: a claim brings nutrition labelling back · FSS-LD-2020 5(3)(c), closing proviso · p. 13

Passage id `FSS-LD-2020:5(3)(c)+2`. This is the in-force continuation of the exemption list. `get_clause(5(3)(c))`
returns the whole clause, with the superseded items left out.

> "However, nutritional information shall be required in the above -mentioned products if a nutrition or health claim is made on the label."

*Why it matters:* this is a provision that **modifies** another (spec §5 step 2). A product exempt from
nutrition labelling loses the exemption once it carries a claim. For a breakfast cereal this changes
nothing, because it is not exempt. For an exempt product carrying "source of protein", the missing panel
is itself a finding.

### P8: small packs drop the panel · FSS-LD-2020 8(1) · p. 22

Passage id `FSS-LD-2020:8(1)`.

> "(1) Where the surface area of the package is not more than 100 square centimetres, the label of such package shall be exempted from the requirements of list of ingredients, Lot Number or Batch Number or Code Number, nutritional information, labelling of irradiated food, declaration of food additives, License no and logo the name and complete address of the importer and instructions for use, but these information shall be given on the multi-unit packages."

*Why it matters:* this is a possible **exemption** (F7). A pack of ≤ 100 cm² with a protein claim but no
panel brings P7 and P8 into tension, and no clause in the corpus resolves it. It should go to
`regulatory-review`, not be answered.

### P9: tolerance on the declared value · FSS-LD-2020 5(3)(d) · p. 14

Passage id `FSS-LD-2020:5(3)(d)~substituted` (re-operationalised w.e.f. 1 Jan 2023; replaces "maximum minus 10 percent").

> "(d) The compliance to quantity of declared nutrients on the label shall have the tolerance of ± 20 percent of the value for that nutrient declared on the label at any point in time within declared shelf life of the product."

*Why it matters:* this is a borderline aid. It governs analysed vs. declared content, not the claim
threshold, so the system should **not** use it to stretch a declared value past P1. A declared value
near the threshold is a reason to escalate.

### P10: how protein is calculated · FSS-LD-2020 5(3)(e)(ii) · p. 14

> "(ii) Calculation of Protein - The amount of protein to be listed should be calculated using the formula: Protein = Total Kjeldahl Nitrogen x 6.25 (Unless a different factor scientifically justified, may be used) Provided that for calculating protein content in milk a conversion factor of 6.38 needs to be used."

The energy factor for the per-100-kcal basis is in 5(3)(e)(i): "(D) Protein 4 kcal/g".

### P11: health supplements are governed elsewhere · FSS-AC-2018 Schedule I, Note 1 · p. 15

Passage id `FSS-AC-2018:Schedule I, notes~substituted`.

> "Note 1: Nutrient content claims for food products falling under health sup plement categories shall be governed by Food Safety and Standards (Health Supplements, Nutraceuticals, Food for Special Dietary Use, Food for Special Medical Purpose, Functional Food and Novel Food) Regulations, 2016."

*Why it matters:* a protein powder sold as a health supplement is **out of corpus** (F7). It must
escalate, not be answered from Schedule I.

### P12: the only pointer from Labelling to Claims · FSS-LD-2020 5(1)(c) · p. 5

> "(c) It may additionally have a “coined”, “fanciful”, “brand” or “trade name” subject to compliance of Food Safety & Standards (Advertising and Claims) Regulation 2018."

*Why it matters:* this is evidence for the spec's statement that the labelling regulation does not point
to claim conditions. Its one cross-reference is about names, not nutrition claims.

## How the agent should get there (what demo item 10 shows)

1. `corpus_search("source of protein claim")` without a filter reaches P1 directly in hybrid retrieval.
   A plain labelling query, `corpus_search("protein declared in nutritional information")` with
   `regulation=FSS-LD-2020`, returns P6. It cannot return P1, because that filter excludes the Claims
   regulation.
2. Reflect: "the label makes a *claim*; does another regulation set a condition for it?"
3. `corpus_search("source of protein claim condition", regulation=FSS-AC-2018)` returns P1 (and P2, P4).
   Then `clause_lookup(FSS-AC-2018, "5(3)")` retrieves P2.
4. Compare `nutrition.protein_g` (per 100 g) with P1. The comparison needs the protein RDA (open
   question below). Cite both regulations: P1 and P6, with P2.
5. Verify: every quote is a substring of the cited passage (A3).

Measured retrieval for three phrasings of this question is in `docs/report/retrieval-and-performance.md`.
Dense search alone misses P1 for two of the three; hybrid search finds it in the top 5 for all three.

## Open question for the team (decide before the test values are final)

**Where does the protein RDA come from?** P1 is expressed in % of RDA, and P5 sends us to ICMR, which is
not in the corpus. Options:

1. **Add the ICMR reference value as a configured, cited external reference.** The team reads the number
   from the ICMR-NIN publication and records the edition, table and value in a decision record. The
   system cites it as "external reference, not FSSAI text". Then the system can answer.
2. **Escalate whenever the outcome depends on the RDA value.** In practice, always escalate for this
   claim. That is safe, but demo #10 then shows an escalation rather than a comparison.
3. **Both:** compare with the configured value, but escalate when the declared value is within ±20 % of
   the threshold (P9 makes values near the line uncertain anyway).

The recommendation is option 3. Whatever is chosen, the numeric RDA must come from the ICMR document read
by a person, and is **TO VERIFY**: it is not in this corpus and must not be "recalled" by an LLM
(AGENTS.md rule 4).

**For the test values (Vihaan, V1.3).** Choose declared protein values far enough from the threshold that
the outcome is the same for any defensible RDA figure. One clearly below (the `protein-claim-low` load
payload uses 2.5 g/100 g) and one clearly above (14 g/100 g). Add one case that must escalate: a
borderline value, a pack ≤ 100 cm² (P8), or a health supplement (P11). Express the threshold once,
symbolically, as `0.10 × RDA_protein g per 100 g` for solids, until the team fixes the RDA source.

## Interpretation notes (for review, not asserted as law)

- **"or 5% of RDA per 100 kcal".** The row reads as two mass/volume bases plus an energy basis, joined by
  "or". The likely reading is that meeting either the per-100 g (solids) basis or the per-100 kcal basis
  is enough. The table does not say so explicitly. If the two bases disagree for a test product, that is
  a case for `regulatory-review`.
- **Solid vs liquid** is decided by the request's `nutrition.basis` (`per_100g` / `per_100ml`). Breakfast
  cereals are solids.
