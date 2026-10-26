# 202: The verifier: deterministic checks first, one LLM support check, specific retry hints

- **Owner:** Vihaan · **Status:** Accepted
- **Requirement:** A3 (verify every answer against retrieved passages; citations must resolve; else retry or
  escalate), A2 (a second agent with its own prompt, tools and state), spec §5 step 4 · Code: `libs/verification/`

## Context

The researcher (Namith) hands over a `ResearchDossier`: findings with citations, plus every passage it retrieved.
The verifier decides `accept`, `retry` (with a hint) or `escalate`. Two failure modes matter. A citation that does
not resolve is a hallucinated source. A citation that resolves but reaches the wrong conclusion is the pitfall
noted in Vihaan.md, where "cited correctly, wrong conclusion" slips past an existence check.

## Options

| Option | For | Against |
|---|---|---|
| Citation existence only (the fake) | Cheap, deterministic | Misses wrong conclusions from correct quotes |
| LLM checks everything | Catches paraphrase and reasoning errors | Costs a step per finding; the judge can be wrong or talked round; unavailable when the provider is down |
| **Deterministic checks, then one batched LLM check for what they cannot decide** | Cheap; the checks that matter most cannot be argued with; one step per attempt | The LLM check is advisory when its output is unparseable (see below) |

## Decision

1. **Citations resolve** (the `resolve_citation` tool, deterministic). The quote must be a substring of a passage
   in `dossier.passages`, after folding whitespace, curly quotes and dashes. Case is *not* folded, because changing
   case is editing the regulation. This check alone fails a finding.
2. **Numbers** (deterministic). For a nutrient claim, the condition is re-read *from the cited passage*: claim word
   (Schedule I's own headings: Source, High/Rich, Low, Free), threshold, unit and basis (per 100 g / ml / kcal). It is
   compared with the request's declared value independently of the researcher. Outcomes:
   - `mismatch` → retry
   - `needs_reference` (a % of RDA, with no value in the text) → escalate
   - `bases_disagree` → escalate
   - `borderline` (declared × (1 ± 20 %) spans the threshold; FSS-LD-2020 5(3)(d)) → escalate

   No threshold is written in the code; every number comes from the passage at run time.
3. **Support** (one LLM call per attempt, prompt `verifier_support@1.0.0`). Does each cited passage, with the
   request facts, entail the finding's status? It runs only for findings that passed 1 and 2. Label text reaches
   it only inside `<label_data>` blocks.
4. **Action.** Escalation signals or an escalate-class problem → `escalate`. A fixable problem → `retry` with a
   hint, unless this is the last attempt, in which case `escalate`. Otherwise `accept`. Hints are specific ("FSS-LD-2020:5(14) quote
   is not verbatim; copy the words exactly from FSS-LD-2020 5(14)", "clause_lookup FSS-AC-2018 5(3)") and end with a
   strategy that changes per attempt (clause lookup first, then the other regulation), so a retry is never the same
   search again.
5. **`clause_lookup`** runs only for a citation to a passage that was never retrieved. It tells the hint whether
   the clause exists. It never makes a finding supported, because A3 requires text retrieved *by the researcher in
   this run*.
6. **Budget.** `resolve_citation` touches no corpus, so it is listed in the verification step instead of recorded
   as a tool step, where it would spend the run's tool-call budget. A lookup runs only if the LLM check, the
   verification step, the router and the output filter still fit. If the LLM check itself does not fit, the run
   escalates rather than accepting unchecked.

## Consequences

- The prompt is the verifier's own file (`fssai_verification/prompts/verifier_support/`), in the same format and tag
  convention as `fssai_prompts`. It can move into Namith's store later without code changes beyond the loader.
- **Known limit (shortcut):** an unparseable or missing judgement *abstains*. The finding then stands on checks 1
  and 2, and the abstention is recorded in the trace. Tighten it to "escalate on abstain" once the judge is
  calibrated against hand labels (`python -m fssai_eval calibrate`); `VERIFIER_SUPPORT_CHECK=off` makes the
  deterministic-only mode explicit.
- The numeric parser understands Schedule I's row format. A claim condition written in another form (e.g. FSS-AC-2018
  6(1) non-addition of sugars) is not re-derived by numbers; the LLM check covers it.
- The faithfulness metric reuses checks 1 and 2 (decision 204), so with this verifier on, offline faithfulness is
  partly circular. The LLM and TruLens judges are the independent measure.
