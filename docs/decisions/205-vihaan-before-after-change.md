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
PROMPT_RESEARCHER_VERSION=1.0.0 python -m fssai_eval run --tag researcher-1.0.0 --judge llm
PROMPT_RESEARCHER_VERSION=1.1.0 python -m fssai_eval run --tag researcher-1.1.0 --judge llm
python -m fssai_eval compare researcher-1.0.0 researcher-1.1.0
```

with `IMPL_PIPELINE=fssai_agents.graph:LangGraphPipeline`, `IMPL_RESEARCHER=...LangGraphResearcher`,
`IMPL_RETRIEVER=...FaissRetriever`, `IMPL_VERIFIER`/`IMPL_ROUTER` on, and `IMPL_LLM` the gateway or `DevLLMClient`.

## Consequences

- The results files go in `eval/results/` and the table goes in `docs/report/verification-and-evaluation.md`.
- What is measured so far (no key here): the harness itself, run on the contracts' fakes, with the fake verifier and
  router vs `AgentVerifier` + `RuleRouter`. Route accuracy 0.310 → 0.345 and escalation recall 0.308 → 0.615 on 29
  scenarios. That shows the measurement pipeline works, not prompt quality.
