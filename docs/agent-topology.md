# Agent topology (A2)

Owner: Namith · Requirement: A2 (and the structure behind A1, A3, F7) · Status: draft for Evaluation 1

This page says which agents exist, what each one owns, how they hand work to each other, how the
loop is bounded, and what happens when something fails mid-run. The hand-off types are in
`packages/contracts/fssai_contracts/schemas.py`; the order of steps is fixed by
`packages/contracts/fssai_contracts/pipeline.py` and `LangGraphPipeline` must behave identically at the edges.

## 1. Diagram

```mermaid
flowchart TD
    REQ[LabelCheckRequest<br/>already validated by the gate] --> GIN
    GIN[Guardrails: screen_input<br/>injection, toxicity, length] -->|blocked| ROUTE_BLOCK[regulatory-review<br/>reason: input failed screening]
    GIN -->|allowed| CLS
    CLS[Classifier agent<br/>category + claims] -->|in_scope = false| ROUTE_OOS[regulatory-review<br/>reason: category outside corpus]
    CLS -->|Classification| RES
    RES[Researcher agent<br/>tool loop: search, clause lookup, field lookup] -->|ResearchDossier| VER
    VER[Verifier agent<br/>every citation must resolve] -->|Verdict: retry + hint<br/>attempt < max| RES
    VER -->|Verdict: accept or escalate<br/>or retries used up| RTR
    RTR[Router<br/>clear / revise / review] --> GOUT
    GOUT[Guardrails: filter_output<br/>no approval wording, never upgrades a route] --> RESULT[RunResult]
    ROUTE_BLOCK --> RESULT
    ROUTE_OOS --> RESULT
```

Deterministic steps (no LLM decides anything): guardrails, router, and the retry edge. The three
agents are the Classifier, the Researcher and the Verifier.

## 2. The agents

| | Classifier | Researcher | Verifier |
|---|---|---|---|
| Owner | Namith | Namith | Vihaan |
| Package | `packages/agents` | `packages/agents` | `packages/verification` |
| Prompts | `classifier` | `researcher` (act), `researcher_draft` | its own |
| Input | `LabelCheckRequest` | `Classification` (+ request, + optional `retry_hint` and `previous` dossier) | `ResearchDossier` + request |
| Output | `Classification` | `ResearchDossier` | `Verdict` |
| Tools | none that it chooses (label text is pre-parsed); rule-based fallback | `corpus_search(query, regulation?)`, `clause_lookup(regulation, clause_id)`, `request_field_lookup(path)` | `resolve_citation`, `clause_lookup` |
| State | none between runs | the dossier: passages, queries, findings, escalation signals, attempt number | per-run only |
| Chooses its own tool calls | no | **yes** (LLM picks the tool at each step, or `finish`) | yes |

Why these are agents and not one prompt in one process: each has its own prompt, its own tool set,
its own state, and they only talk through the hand-off schemas above. The Researcher never sees the
Verifier's reasoning, only its `Verdict` (`action`, `retry_hint`, `escalation_reason`). The Verifier
never sees how the Researcher searched, only what it retrieved and cited.

## 3. The Researcher's loop (spec section 5)

Nodes: `plan` → `act` ⇄ `run_tool` → `coverage` → `draft`.

1. **plan:** deterministic, no LLM step. Seeds suggested searches from the detected claims, the nutrition panel and the package size. The model may follow, reorder or ignore them.
2. **act:** the LLM first writes a short reflection ("does anything I have read modify, condition, define or exempt something? which regulation would hold it?") and then picks one tool, or `finish`. The prompt also lists clause and schedule names mentioned inside retrieved passages that have not been looked up yet. Arguments are validated against an allowlist (regulation must be a known code, `path` must be a field of `LabelCheckRequest`, query length is capped). An invalid or repeated call is replaced by the next unused suggestion, or by `finish`.
3. **run_tool:** `ctx.check_budget(tool_call=True)` first, then the call, then a `tool` step with the full passages (this is what lets a run be rebuilt from its trace, D5). A failing tool is recorded with its error and the loop goes on; it does not kill the run.
4. **coverage:** a safety net for weak models. Every detected claim must have a search that reached the Claims regulation for its condition. If the model finished without one, this node runs it.
5. **draft:** the LLM writes one `Finding` per requirement from the retrieved passages only. Every citation quote is made a verbatim span of the cited passage (whitespace and quote-mark differences are repaired to the passage's own text; paraphrases are dropped). A met or unmet finding that loses all its citations becomes `cannot_determine` with an escalation signal.
   Conflicts, possible exemptions, a missing condition, or a needed value that is not in the corpus go into `escalation_signals`.

The reflection step from the first draft of this page is part of `act`, not a separate node: a separate reflect call would double the LLM calls per round and the step budget (25) is shared by the whole run. Each round is two steps (one LLM call, one tool call), and the number of rounds is capped by what is left of the step budget after reserving steps for the verifier, router and output filter (`RESEARCHER_MAX_ITERATIONS`, `RESEARCHER_STEP_RESERVE`).

**Retry mode.** When the Verifier says `retry`, the Researcher receives `retry_hint` and the
`previous` dossier, keeps what was already retrieved, and must change strategy: clause lookup
instead of search, the other regulation, or narrower queries. `attempt` increases by one.

**Nothing from memory.** The agent may not answer from what it "knows" about FSSAI. A requirement
with no supporting retrieved passage is `cannot_determine` plus an escalation signal.

### How this handles the section 4.1 case

- The claim text "source of protein" does not occur in either regulation (Nishkal's passages page).
  A literal match finds nothing, so the Researcher searches by nutrient plus claim level
  ("protein", "source", conditions for nutrient content claims), which reaches FSS-AC-2018
  Schedule I, item 11 and regulation 5(3).
- The Labelling regulation never points to that condition. The step that finds it is the reflection in `act`
  applied to the detected claim (and, if the model skips it, the `coverage` node) ("what regulation conditions a nutrient content claim?"), followed
  by a search restricted to FSS-AC-2018.
- The condition is a percentage of the RDA, and neither regulation states the RDA value. The
  Researcher must not fill it in from training data. Unless the retrieved text supplies the value,
  the finding is `cannot_determine` with an escalation signal naming the missing reference value.
  The agreed handling of this gap is for the team to settle in the Evaluation 1 plan (open
  question in `docs/eval1/section-4.1-passages.md`).

## 4. Loop bounds

All bounds are enforced by `RunContext.check_budget()` and configured in `.env` (`RUN_*`).

| Bound | Default | Env | Where checked |
|---|---|---|---|
| Steps per run (all agents) | 25 | `RUN_MAX_STEPS` | before every step |
| Tool calls per run | 15 | `RUN_MAX_TOOL_CALLS` | before every tool call |
| Wall clock per run | 90 s | `RUN_MAX_WALL_S` | before every step, and the LLM client caps each call by `remaining_s()` |
| Research attempts (Researcher ⇄ Verifier) | 3 | `RUN_MAX_RESEARCH_ATTEMPTS` | the retry edge |
| LangGraph `recursion_limit` | set from `RUN_MAX_STEPS` | derived | graph invocation |

Hitting any bound raises `BudgetExceeded`; the pipeline catches it and returns an **incomplete**
run (see section 5).

## 5. What happens when something fails mid-run

Rule for everything below: a run that did not finish is never returned as a confident answer.
It returns `complete=false`, route `regulatory-review`, and the reason.

| Failure | Detected by | What happens | Result |
|---|---|---|---|
| Input contains an injection or toxic text | `screen_input` | Run stops before any agent starts | `regulatory-review`, flags listed, `complete=true` |
| Category outside the corpus, or label text contradicts the declared category | Classifier `in_scope=false` | No research | `regulatory-review`, category named |
| Classifier LLM returns bad JSON | parse failure | One repair retry, then the rule-based detector answers; rationale says "rule-based fallback" | Run continues, noted in the trace |
| LLM provider down or circuit breaker open, in Classifier | `ProviderUnavailable` | Classifier degrades to rules and the run continues; the Researcher will hit the same outage | See next row |
| LLM provider down or breaker open, in Researcher or Verifier | `ProviderUnavailable` | No further model calls; nothing partial is trusted | `complete=false`, `regulatory-review` (demo item 8) |
| Retriever fails, or the index is missing or empty | exception, or zero passages | Researcher records the tool error; with no passages it cannot ground a finding | `cannot_determine` + escalation signal, so `regulatory-review` |
| A tool call returns nothing useful | empty `passages` | the next `act` step changes the query or regulation; repeated misses end in an escalation signal | Escalate, never a guess |
| Model stops searching early, or answers with bad JSON | parse failure, or `finish` with a claim uncovered | Next suggested search runs instead; `coverage` still searches the Claims regulation for each claim | Run continues, noted in the trace |
| Researcher produces a citation that is not verbatim | Researcher's own quote check, then Verifier | Repaired or dropped; if the finding loses its support it becomes `cannot_determine` | Verifier `retry` or `escalate` |
| Verifier says `retry` | `Verdict.action` | Researcher re-runs in retry mode with the hint | Up to 3 attempts |
| Still unverified after the last attempt | pipeline | Verdict becomes `escalate` ("still unverified after N attempts") | `regulatory-review` (demo item 6) |
| Step, tool-call or wall-clock bound hit | `BudgetExceeded` | Loop stops where it is | `complete=false`, `regulatory-review` |
| Worker process dies mid-graph | queue job times out | The job is re-queued or marked failed by the worker (Vismay's service). Without checkpointing, the run restarts from the beginning | Run status `failed`, never a half answer. Checkpointing is an extra (see below) |
| Output filter finds approval wording, or a route that its verdict does not support | `filter_output` | Wording blocked; route forced up to `regulatory-review`. It never moves a route toward `clear-for-print` | Safer route than the one proposed |

**Hand-off failure.** If an agent returns something that does not parse as its output schema, that
is treated as the agent failing: Classifier falls back to rules; Researcher or Verifier output that
fails validation counts as an unverified attempt (retry, then escalate).

**Extra (not promised for Evaluation 1):** LangGraph checkpointing in Postgres or Redis so a run
interrupted mid-graph resumes at its last node instead of restarting. If built, this table's
"worker dies" row changes to "resumes".

## 6. What is recorded for every run (D5)

- A `guardrail` step for each screen and each output filter.
- A `classification` step and the classifier's `llm` steps.
- A `tool` step for every Researcher tool call, with the **full passages returned**.
- `llm` steps with prompt name, prompt version, tokens and cost (recorded by the LLM client).
- A `verification` step and a `routing` step.
- `RunResult.prompt_versions` lists the version of every prompt used.

Per-agent Prometheus metrics (A6) are labelled by `agent`: runs and successes, steps and tool calls
per run, per-step and end-to-end latency, retries.

## 7. Open points for the team

1. RDA reference value for nutrient content claims (section 3). Needs a decision before the
   Researcher can reach `met` or `unmet` on the section 4.1 case instead of `cannot_determine`.
2. Whether the Verifier calls `clause_lookup` itself or only resolves citations against the dossier (Vihaan).
3. Whether `recursion_limit` should be per agent or per run.
