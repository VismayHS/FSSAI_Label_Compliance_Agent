# 102: The researcher searches every requirement before it drafts (Namith)

Status: accepted, 2026-10-27. Requirements: A1, A2, F4, F5.

## Context

A live section 4.1 run with the real LLM (Groq, researcher 1.1.0, run `a4702e8fcf3f4c44aa452896f171a129`) made two
searches and then drafted 11 findings. Nine were `cannot_determine` with "no passage was provided" (allergen,
ingredients, veg mark, licence, manufacturer, date marking, batch, whole grains), because retrieval was a tool the
model chose and it chose `finish`. The router sends any `cannot_determine` finding to regulatory-review (R5), so
every label ended in review and demo #2 could only show escalations.

## Decision

1. A deterministic `sweep` node runs before the model acts: one Claims-regulation search per detected claim and five
   broad Labelling-regulation searches that each cover two or three requirements. The model's `act` loop then only
   adds follow-up searches (cross-references, exemptions).
2. Broad, grouped queries instead of one query per requirement. The verifier now runs in every run and its
   `clause_lookup` calls count against `RUN_MAX_TOOL_CALLS`; one query per requirement used 11 or more of the 15 tool calls.
   Passage text in the prompts is capped in total (`RESEARCHER_DRAFT_CHARS`, `RESEARCHER_ACT_CHARS`), because about 30 retrieved
   passages at full length would be about 20k tokens against Groq's 8k tokens a minute.
3. The draft prompt (`researcher_draft` 1.1.0) lists the researched and not-researched requirement ids and may write
   findings only for the first group. Code enforces it: an uncited finding for an unsearched requirement is dropped
   (logged), a requirement the budget could not cover becomes an escalation signal, so a label is never cleared on
   something nobody checked.
4. Housekeeping stays out of `escalation_signals`, because the router escalates on any signal (R3). A partly dropped
   citation list is logged; only a finding left with no citation, an unsearched requirement, or an undrafted one escalates.
5. Step reserve now includes later research attempts (`RESEARCHER_RETRY_STEPS=3` each), so a first attempt cannot
   spend what a retry needs. The limits were not raised.

## Measured (scripted LLM, real verifier, router and guardrails; `packages/agents/tests/test_step_budget.py`)

| Scenario | Steps (limit 25) | Tool calls (limit 15) |
|---|---|---|
| Verified first time, label clears | 15 | 6 |
| Verifier rejects twice, 3 attempts | 23 | 6 |
| Model searches on every `act`, 3 attempts | 25 | 9 |

These count steps, not time. The sweep adds no LLM call, so the wall-clock cost is retrieval only; the 90 s check
against real Groq latency is still to be run (see the runbook entry).

## Rejected

- One search per requirement: 11+ tool calls, starves the verifier.
- Raising `RUN_MAX_STEPS` / `RUN_MAX_TOOL_CALLS`: hides the cost; agreed with Vismay to try fewer, broader queries first.
- Telling the model harder to search (prompt only): a checklist already exists in 1.1.0 and the live run still stopped at two searches.

## Consequences and open points

- Fewer steps for the model's own reasoning: on a first attempt it gets one `act` round under the default limits.
- Broad queries may retrieve a topic less precisely than a dedicated one; the effect shows in the eval set as
  `cannot_determine` with a named gap. Fix by moving that topic to its own query (edit `REQUIREMENT_GROUPS`).
- The protein claim itself still routes to review while the RDA reference value is undecided (team question, Nishkal and Vihaan).
