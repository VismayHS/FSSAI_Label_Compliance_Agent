# 103: Researcher prompt comparison, 1.0.0 against 1.1.0 (Namith)

Status: Accepted, measured 2026-11-06 (00:45-01:20 IST; the file stamps are UTC) by Vismay on Namith's tooling. Requirements: L2 (versioned prompts, two variants compared), L3.

## Context

Two versions of the researcher prompt (with its paired draft prompt) exist: 1.0.0 (plain rules) and 1.1.0 (adds an
explicit checklist for provisions that modify, condition or exempt another). Both were run through the same evaluation
set (`packages/eval/scenarios.jsonl`, 8 scenarios completed in 1.1.0,
8 in 1.0.0), the same model, retriever, verifier, router and limits. Only
`PROMPT_RESEARCHER_VERSION` and `PROMPT_RESEARCHER_DRAFT_VERSION` differed. Results: `packages/eval/results/researcher-1.0.0.json`
and `researcher-1.1.0.json` (judge: reference; git sha ef1c605 / ef1c605).

## Result

| Metric | 1.0.0 | 1.1.0 | Difference |
|---|---|---|---|
| Route accuracy | 0.50 | 0.50 | 0 |
| Section 4.1 case reaches FSS-AC-2018 | 1.00 | 1.00 | 0 |
| Mean tool calls per run | 5.38 | 5.62 | +0.25 |
| Groundedness / faithfulness | 1.00 / 1.00 | 1.00 / 1.00 | +0.00 / +0.00 |
| Hallucination rate | 0.00 | 0.00 | 0 |
| Unsafe clear rate | 0.00 | 0.00 | 0 |
| Citation resolution | 1.00 | 1.00 | 0 |
| Mean LLM calls per run | 2.62 | 2.75 | +0.12 |
| Mean cost per run (USD) | 0.00 | 0.00 | 0 |

Verdict: **1.0.0**. finding_accuracy: 0.46 (1.0.0) vs 0.38 (1.1.0), 1.0.0 better. mean_tool_calls: 5.38 (1.0.0) vs 5.62 (1.1.0), 1.0.0 better.

Safety metrics decide first (a prompt that clears labels it should not, or states unsupported things, loses whatever
else it gains), then correctness, then cost. Scenarios cut short by the provider's rate limit are counted separately
and never scored (`provider_failures`: 0 / 0).

## What this does and does not show

- With 8 scenarios, a difference of one scenario is 12.5 points
  of route accuracy. Treat small gaps as noise.
- Each variant ran once; a free-tier model is not deterministic, so a rerun can differ.
- The section 4.1 finding stays `cannot_determine` until the RDA reference value is decided (team question), so that
  row measures whether the claim was researched, not whether it was decided.
- **A subset, not the whole set.** 8 of the 30 scenarios per variant (`--scenarios`): both §4.1 traps, one
  clear-for-print claim, one revise claim, one missing mandatory item, one clean label, the small-pack exemption and the
  injection. 16 real runs is one key's daily budget (Groq: 200,000 tokens per day per model; incident
  `2026-10-30-vismay-groq-daily-token-cap`). The key reached 199,625 of 200,000 straight after.
- **Measured on the host, BM25 only.** The embedding model's cache did not survive the copy out of the Compose volume
  (symlinks), so the retriever served its BM25 half for both variants. Same for both, so the comparison is fair, but
  the absolute numbers are not the hybrid retriever's.
- **Before the whitespace grounding fix.** Every clear/revise scenario (4 of 8) escalated with R1 in *both* variants
  because grounding dropped quotes of words the PDF text splits ("dis played"); fixed afterwards in commit 2eb5101
  (incident `2026-11-06-vismay-grounding-dropped-real-quotes`). Route accuracy 0.50 therefore measures that bug, not
  the prompts. The "..." fix was already in.
- **Offline judge.** Decision 205 planned `--judge llm`; the token budget left none for a judge, so the deterministic
  reference judge scored these runs. It decided faithfulness for only 1 of 42 decisive statements, so the
  faithfulness 1.00 is weak evidence. Groundedness and citation resolution (verbatim checks) are fully measured.

## Decision

Keep **1.0.0** as the default (already pinned: `PROMPT_RESEARCHER_VERSION=1.0.0` in `.env.example`). The modifier
checklist in 1.1.0 changed no route and no safety metric, cost a quarter more tool calls per run, and got one finding
fewer right (0.38 vs 0.46 finding accuracy, about one finding of 13). That gap is inside the noise of 8 scenarios, so
the deciding reason is the cheaper, simpler prompt with nothing lost. Both variants already reach FSS-AC-2018 on the
§4.1 cases: the deterministic sweep (decision 102) searches the claim condition whatever the prompt says, which is
why a prompt-level checklist adds little. Rerun on all 30 scenarios after the grounding fix, over two days on one
key, before treating the difference as real.
