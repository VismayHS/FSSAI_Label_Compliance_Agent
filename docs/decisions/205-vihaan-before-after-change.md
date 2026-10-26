# 205: Before/after experiment: researcher prompt 1.0.0 → 1.1.0

- **Owner:** Vihaan (with Namith) · **Status:** Proposed. The harness is ready; the measured numbers need a
  free-tier LLM key in `.env` (the fakes cannot exercise a prompt).
- **Requirement:** L3 (measure before and after one deliberate change, all four metrics with deltas), L2 (compare
  ≥ 2 prompt variants)

## Context

L3 asks for one deliberate change, measured on the whole eval set. Candidates from the team:

| Change | Owner | For | Against |
|---|---|---|---|
| **Researcher prompt 1.0.0 → 1.1.0** (adds a modifier checklist: "does another provision modify, condition or exempt this?") | Namith | Targets spec §5 step 2 directly, the step the eval's `trap` scenarios test; Namith already built the variant (M3.2); serves L2 at the same time | Needs a real LLM |
| Retrieval `dense` → `hybrid` | Nishkal | Already measured at retrieval level (recall in his report) | Its effect on findings is indirect |
| Chunk size | Nishkal | Classic RAG lever | The index is clause-aware (decision 002), so chunk size barely changes it |

## Decision

Measure **researcher 1.0.0 → 1.1.0**, with everything else fixed (index, retriever mode, verifier, router, judge).
It changes the step the project's obstacle is about, and the `trap`, `exemption` and `cross-regulation` tags show
where.

```bash
PROMPT_RESEARCHER_VERSION=1.0.0 python -m fssai_eval run --tag researcher-1.0.0 --judge llm --pause-s 75
PROMPT_RESEARCHER_VERSION=1.1.0 python -m fssai_eval run --tag researcher-1.1.0 --judge llm --pause-s 75
python -m fssai_eval compare researcher-1.0.0 researcher-1.1.0
```

**Free-tier budget.** One real run uses about 8-12.5k tokens, and Groq's free tier allows 8,000 tokens a minute
and 1,000 requests a day per model. So scenarios run one at a time with a pause (`--pause-s` or `EVAL_PAUSE_S`),
which comes to about 40 minutes per variant for 30 scenarios. Results are written after every scenario. A run the
provider cut short (`ProviderUnavailable`: 429 or outage) is marked `provider_failed`, counted but never scored as
an escalation. Rerunning the same command with `--resume` runs only those, so the day's request quota is not spent
twice. Start the second variant on a fresh day if the first used more than half the quota.

**Precondition.** Namith's researcher fix (it searches for every requirement it reports) must be on `main`. Without
it most scenarios end `cannot_determine`, and the comparison measures nothing.

with `IMPL_PIPELINE=fssai_agents.graph:LangGraphPipeline`, `IMPL_RESEARCHER=...LangGraphResearcher`,
`IMPL_RETRIEVER=...FaissRetriever`, `IMPL_VERIFIER`/`IMPL_ROUTER` on, and `IMPL_LLM` the gateway or `DevLLMClient`.

## Consequences

- The results files go in `eval/results/` and the table goes in `docs/report/verification-and-evaluation.md`.
- What is measured so far (no key here): the harness itself, run on the contracts' fakes, with the fake verifier and
  router vs `AgentVerifier` + `RuleRouter`. Route accuracy 0.310 → 0.345 and escalation recall 0.308 → 0.615 on 29
  scenarios. That shows the measurement pipeline works, not prompt quality.
