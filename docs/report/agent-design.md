# Agent design: classifier, researcher, guardrails, prompts

Owner: Namith · Requirements: F3, F4, F5, A1, A2, A6, L2, L4, D8 · Status: draft; the numbers marked TODO come from the evaluation run

## 1. Problem and scope of this part

The section 4.1 case ("source of protein") depends on a provision the request never names. The
labelling regulation (FSS-LD-2020) does not point to the claim condition, which sits in the
Advertising and Claims regulation (FSS-AC-2018). A single retrieval pass returns passages that resemble
the question, so it misses that condition. This part of the system is the reasoning layer that
finds it, and that stops safely when it cannot.

## 2. Topology (A2)

Guardrails (input) -> Classifier -> Researcher <-> Verifier -> Router -> Guardrails (output).
Three agents with different prompts, tools and state, joined only by typed hand-offs
(`LabelCheckRequest`, `Classification`, `ResearchDossier`, `Verdict`). Guardrails, router and the
retry edge are deterministic. Full diagram, per-agent table and the failure table are in
`docs/agent-topology.md`.

| Agent | Tools it chooses | Output |
|---|---|---|
| Classifier | none (rule-based fallback) | category, in-scope flag, detected claims |
| Researcher | `corpus_search`, `clause_lookup`, `request_field_lookup` | dossier: passages, queries, findings, escalation signals |
| Verifier (Vihaan) | `resolve_citation`, `clause_lookup` | accept / retry with hint / escalate |

## 3. The Researcher loop (A1, F4, F5)

`plan` -> `act` <-> `run_tool` -> `coverage` -> `draft`. In `act` the model writes a short
reflection ("does anything I read modify, condition, define or exempt something, and which
regulation holds it?") and then picks a tool or `finish`. This reflection is what leads from a
detected claim to FSS-AC-2018. The `coverage` node is a safety net: every detected claim must have a
search that reached the Claims regulation. On a Verifier `retry` the Researcher keeps its earlier
passages and must change strategy (clause lookup instead of search, the other regulation, narrower queries).

Bounds (A1): 25 steps, 15 tool calls, 90 s wall clock per run, 3 research attempts, all from `.env`.
Tool arguments are checked against an allowlist before a call is made.

Structured output: every reply that must be JSON goes through `ask_structured`: parse, check the shape, and if it is unusable show the model its own reply and what was wrong, once, only if the step budget allows. Outcomes are counted (`valid`, `repaired`, `failed`, `skipped`) and drawn on the agents dashboard. The draft step repairs; the act step does not, because an unusable act reply already falls back to the next suggested search.

Grounding: citation quotes are repaired to verbatim spans of the cited passage or dropped. A finding that
loses all its citations becomes `cannot_determine` with an escalation signal. The agent never uses remembered rules.

## 4. Guardrails (L4)

See decision 101. Input: heuristics over every string in the request (plus folded and base64-decoded
variants), a toxicity lexicon with an optional model, and an optional LLM judge. Output: removes approval
wording, never moves a route toward `clear-for-print`, requires an accepted verdict for it, and drops
citations that do not resolve to this run's trace. Structural defences do not depend on detection: label
text is only ever passed inside data blocks and tool arguments are allowlisted.
Red-team set (`packages/guardrails/tests/attacks.yaml`): 44 attacks, each placed in one field and required to be flagged in that field, and 16 pieces of real label copy that must not be flagged. The attacks cover instruction override, role-play, authority role-play, fake system lines and chat tokens, delimiter escape, base64, leetspeak, zero-width and full-width tricks, six languages, tool-call text and tool JSON, and data exfiltration. CI prints the block rate on every run (`blocked 44/44 (100%); false positives 0/16`) and a test fails if either figure moves. The second round of attacks found five gaps in the first rule set (authority role-play, "no review needed", tool names in prose, tool JSON, exfiltration); each got a rule and a clean-copy fixture so ordinary wording such as "Visit https://..." or "Send your feedback to care@..." stays allowed.
Known gap: an unseen paraphrased instruction passes the heuristics; the judge is the second layer, and the structural defences (data blocks, allowlisted tool arguments, verbatim citations, an output filter that can only lower a route) hold even when detection fails.

## 5. Prompt versions (L2)

Prompts are files under `packages/prompts/fssai_prompts/prompts/<name>/<version>.yaml`, each starting with
`[prompt:<name>@<version>]`, selected by `PROMPT_<NAME>_VERSION`; the version is recorded on every LLM step.

Comparison: researcher 1.0.0 (plain rules) against 1.1.0 (adds an explicit modifier checklist). Both run
on the same evaluation set with the same model.

| Metric | 1.0.0 | 1.1.0 | Difference |
|---|---|---|---|
| Route accuracy | TODO | TODO | TODO |
| Section 4.1 case reaches FSS-AC-2018 | TODO | TODO | TODO |
| Mean tool calls per run | TODO | TODO | TODO |
| Groundedness / faithfulness | TODO | TODO | TODO |

Result: TODO (which variant, on which metric, by how much; see `docs/decisions/` comparison record).

How the comparison is run: `python -m fssai_agents.compare run` runs the evaluation set once per variant with the researcher and its draft prompt pinned together, paced for the provider's token limit and resumable; `python -m fssai_agents.compare report --write` fills this table and writes the decision record, picking the winner by safety metrics first (unsafe clears, hallucination rate), then correctness, then cost.

## 6. Per-agent metrics and runbook (A6, D8)

Prometheus metrics labelled by `agent`: runs and successes, steps and tool calls per run, per-step and
end-to-end latency, retries; dashboard `infra/observability/grafana/dashboards/agents.json`.
`docs/runbook.md` covers provider rate-limited or down (breaker open) and index missing or stale.
Incident log: `docs/incidents/2026-10-26-namith-diverged-branch-merge.md`.

Demo rehearsal: `python -m fssai_agents.demo --api http://localhost:8000` runs demo 2 (a valid request, every citation checked against the passages in its trace, both regulations cited for a claim label) and demo 7 (an injection in `front_of_pack_text`: flagged field, no LLM or tool step, report that does not echo the attack).

## 7. Decisions and what was rejected

- Reflection inside `act` instead of a separate node: a separate call doubles LLM calls against a shared 25-step budget.
- Heuristics as the default injection detector: free and deterministic; a local model or judge costs a download or a step per run (both kept as options).
- Fixed pipeline with one retrieval pass: rejected, it cannot reach the claim condition.

## 8. What did not work

- A real LLM stopped after two searches and drafted 11 findings, nine of them "no passage was provided"; `coverage` only covered claims, so every label ended in review. Fixed by a deterministic `sweep` that searches every claim condition and labelling requirement first, and by limiting findings to searched requirements (decision 102). One query per requirement did not fit the shared tool-call limit once the verifier ran in every run, so the searches are grouped.
- Giving the model a checklist (prompt 1.1.0) did not make it search more; moving coverage into code did.
- The RDA reference value is not in either regulation, so the 4.1 finding is `cannot_determine` unless the team supplies it (open team question).
