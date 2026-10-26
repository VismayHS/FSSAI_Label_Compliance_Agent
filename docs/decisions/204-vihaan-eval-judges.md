# 204: Eval metrics and judges: four definitions, three judges, TruLens yes, RAGAS no

- **Owner:** Vihaan · **Status:** Accepted
- **Requirement:** L3 (≥ 20 scenarios, TruLens, four metrics, before/after), L6 (live scoring) · Code: `eval/`

## Context

L3 asks for groundedness and context relevance (TruLens), faithfulness defined *differently* from groundedness,
and hallucination rate per response (glossary). The eval must run on a free tier, in CI without a key, and
repeatably for before/after comparisons.

## Decisions

1. **The unit is the statement: one finding.** This matches what the system asserts and what a reviewer reads.
2. **Groundedness ≠ faithfulness.**
   - *Groundedness* asks whether the **text** of a statement is supported by the passages it cites. It is 0 if any
     citation fails to resolve verbatim to text retrieved in this run; otherwise it is the judge's support score.
   - *Faithfulness* asks whether the **status** (met/unmet) follows from the cited passages *plus the request's
     declared values*. This is claim-level entailment: numeric claim conditions are re-derived deterministically,
     others are judged.

   A finding can be fully grounded and unfaithful: the right quote with the wrong conclusion. A unit test pins
   exactly that.
3. **Hallucination is counted per response:** a response with at least one unsupported or unfaithful statement.
   The denominator is the responses that make statements, so an early escalation with no statements neither helps
   nor hurts.
4. **Three judges, one interface:**
   - `reference` (offline, deterministic, default): citation resolution plus the scenario's gold supporting clauses.
     It is free and repeatable, so CI and the regression gate use it.
   - `llm`: our own versioned judge prompts through `IMPL_LLM`.
   - `trulens`: TruLens 2.x `groundedness_measure_with_cot_reasons` and `context_relevance_with_cot_reasons` on an
     OpenAI-compatible provider from env.

   Every model call is cached on disk, keyed by judge, prompt version and inputs.
5. **RAGAS is not a dependency.** *Rejected:* `ragas` 0.2.15 and 0.4.3. Both fail to import next to
   `langchain-community` 0.4, which `fssai_retrieval` requires (`ModuleNotFoundError:
   langchain_community.chat_models.vertexai`). RAGAS 0.4 also pulls `openai` 3.x, which breaks TruLens (`openai<2`).
   Pinning older stacks would fork the team's dependency set for one extra metric. The RAGAS-style cross-check is
   instead the judge calibration in `python -m fssai_eval calibrate`: agreement and Cohen's kappa of the judge
   against hand labels.
6. **Scenario quotes are machine-checked** (`eval/tools/check_scenarios.py`): each supporting quote must be verbatim
   text of the clause it names in the built index. Writing the set, the checker caught one quote typed as "no
   sugars" where the corpus reads "n o sugars".

## Consequences

- Offline numbers are lower bounds on what a reading judge would flag. Context relevance offline is "share of
  retrieved passages that are gold clauses", a recall-style proxy, not TruLens's reference-free score.
- With the verifier on, offline faithfulness shares its numeric parser with the verifier (decision 202), so it is
  partly circular. The report says so, and uses `--judge llm` or `trulens` for the independent number.
- Live scoring (`fssai_eval live`) has no gold answer, so offline context relevance is empty there. A model judge
  fills it.
