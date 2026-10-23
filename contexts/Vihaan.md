# Vihaan: Trust & Evaluation

> Your plan, checklist and LLM prompts. **Only you edit this file.** Tick boxes as you go, and add
> notes at the bottom. Read `contexts/LLM_Context.md` first.

## Your mission
You make the system **trustworthy at both ends**:
- **On the way in:** nothing malformed gets in (the data contract, validation, quarantine, rate limiting).
- **On the way out:** nothing unverified gets out (the verifier agent, routing, escalation).

You also **prove it**: you build the evaluation set and metrics that show how good the system
really is, and the feedback loop that keeps measuring it after deployment. The spec says F5 and F7
"hold most of the difficulty", and most of that difficulty sits with you.

**Requirements you own:** F1 (contract), F2, F6, F7, A3, D1, D7 (rate limiting), L3, L6
**Units:** 1 (data contracts, ingestion boundary), 3 (evaluation, monitoring), 4 (agent verification)
**Demo leads:** #4 malformed request quarantined, #5 unanswerable case escalated, #6 self-verification catching an unsupported answer
**Report sections:** data contract, verification design, evaluation method and before/after results, feedback

**Your paths** (edit nothing else):
- `libs/gate/`, `libs/verification/`, `eval/`
- `services/api/app/routers/feedback.py`, `services/api/app/routers/quarantine.py`
- `docs/data-contract.md`, `docs/eval1/section-4.1-test-values.md`
- `observability/grafana/dashboards/quality.json`
- `deploy/postgres/init/*-vihaan-*.sql`
- your section of `.env.example`
- `docs/decisions/*-vihaan-*`, `docs/incidents/*-vihaan-*`
- `docs/report/verification-and-evaluation.md`

## What you depend on, and what you provide

Nothing below blocks you.

| You consume | From | Until it's real, use |
|---|---|---|
| Real clause text for §4.1 | Nishkal (`docs/eval1/section-4.1-passages.md`) | Read the regulation PDFs yourself for the eval set; your scenarios need real quotes anyway |
| `ResearchDossier` from the research agent | Namith | `FakeResearcher`, plus hand-built dossiers in your tests (that's how you test "unsupported answer" cases) |
| `Retriever` (for the verifier's `clause_lookup` tool) | Nishkal | `FakeRetriever` |
| `LLMClient` | Vismay | `DevLLMClient` with your own free-tier key |
| A pipeline to evaluate | Namith | `ReferencePipeline` with fakes now; the runner uses `build("pipeline")`, so it picks up the real one automatically |
| API app to mount your routers | Vismay | Test your routers with a tiny `FastAPI()` + `TestClient` of your own; the real app auto-mounts them |
| `RunStore` (for live scoring) | Vismay | `InMemoryRunStore` |

| You provide | To | Through |
|---|---|---|
| `RequestGate` | Vismay (API) | `IMPL_GATE` |
| `Verifier`, `Router` | Namith (graph) | `IMPL_VERIFIER`, `IMPL_ROUTER` |
| Eval runner CLI + metrics | Namith (L2 comparison), Nishkal (chunking change) | `python -m fssai_eval run ...` |
| `docs/data-contract.md` | everyone; the web client | The published contract |

---

## Prompt 0: start every LLM session with this
```
I'm Vihaan, one of 4 people building the "FSSAI Label Compliance Agent" (a university ML System
Design & AgentOps project). Before anything else, read from the repo:
1. contexts/LLM_Context.md  (project, team, architecture, rules; stable)
2. contexts/Vihaan.md       (my workstream, tasks, status)
3. contracts/fssai_contracts/*.py  (schemas, interfaces, context, fakes, pipeline, registry)

Rules for this session:
- I may only create/edit files under: libs/gate/, libs/verification/, eval/,
  services/api/app/routers/feedback.py, services/api/app/routers/quarantine.py, docs/data-contract.md,
  docs/eval1/section-4.1-test-values.md, observability/grafana/dashboards/quality.json,
  deploy/postgres/init/*-vihaan-*.sql, my section of .env.example, and my docs files in Vihaan.md.
- Never edit contracts/ or other people's paths. If a contract must change, stop and propose the
  exact additive change and why.
- Code against the interfaces; use fakes for others' components and DevLLMClient for a real LLM.
- No credentials, endpoints or model ids in code: env only, documented in my .env.example section.
- Never invent regulation text or thresholds; quote only from the PDFs in corpus/ or docs/eval1/.
- Record verification/routing steps with ctx.record(); every behaviour gets a pytest test.
Summarise my current task in 3 lines, then wait for my go.
```

---

## Phase 0: setup (days 1–2)

- [ ] **V0.1 Set up and create package skeletons.** Run `pip install -e "contracts[test]"` and `pytest contracts -q`. Create packages:
  - `libs/gate` → `fssai_gate`
  - `libs/verification` → `fssai_verification`
  - `eval/` → `fssai_eval`

  Each needs its own `pyproject.toml` and a smoke test. Open your first PR.

## Phase 1: Evaluation 1 (week 1)

- [ ] **V1.1 Publish the data contract (F1, D1).** Write `docs/data-contract.md` covering:
  - **Fields:** every field of `LabelCheckRequest` with type, unit, whether required, range and permitted values.
  - **Permitted categories:** the one category we chose plus explicit "unsupported" handling.
  - **Cross-field rules**, for example:
    - `per_100ml` basis needs a `ml`/`l` net-quantity unit,
    - `serving_size` and `serving_unit` come together,
    - added sugars ≤ total sugars ≤ carbohydrate,
    - saturated + trans fat ≤ total fat,
    - energy roughly consistent with 4/4/9 kcal/g within a tolerance you justify,
    - claims present ⇒ the relevant nutrient is declared.
  - **Error format and quarantine behaviour.**
  - **Versioning:** use `schema_version`.

  Export JSON Schema to `docs/data-contract.schema.json`.
  ```
  (after Prompt 0) Draft docs/data-contract.md per Vihaan.md V1.1 from fssai_contracts.schemas.LabelCheckRequest.
  For every field: type, unit, required, range (justify ranges briefly), permitted values. List each
  cross-field rule with an id (XF-01...), a plain-English statement and an example violation. Define
  the 422 error body (list of FieldError{loc,message,code}) and quarantine record format. Add a script
  eval/tools/export_schema.py that writes docs/data-contract.schema.json from the pydantic model plus
  our extra constraints as JSON Schema keywords where possible.
  ```
- [ ] **V1.2 Build the gate (F2, D1).** `fssai_gate.gate:RequestGate`:
  - Order: rate limit → schema/type → ranges → categories → cross-field rules.
  - It collects **all** field errors, not just the first.
  - Rejects go to quarantine with the raw payload, client id, errors and timestamp. Start in memory, then use a Postgres table via `deploy/postgres/init/20-vihaan-quarantine.sql`.
  - Only accepted requests get `request` set.
  - **No agent run may ever start on a reject.** The API only enqueues when `accepted`.
  ```
  (after Prompt 0) Implement fssai_gate.gate:RequestGate satisfying the RequestGate interface per
  Vihaan.md V1.2 and docs/data-contract.md. Each cross-field rule is a small function with its XF id
  used as FieldError.code. Quarantine store behind a tiny interface: InMemoryQuarantine (tests) and
  PostgresQuarantine (env DATABASE_URL). Rate limiter: Redis token bucket keyed by client_id with
  RATE_LIMIT_PER_MIN and RATE_LIMIT_BURST from env; fakeredis in tests; on limit return
  GateDecision(accepted=False, rate_limited=True, retry_after_s=...). from_registry() builds from env.
  Tests: each XF rule, multiple errors collected, quarantine row written, rate limit trips.
  ```
- [ ] **V1.3 Write the §4.1 test values.** Write `docs/eval1/section-4.1-test-values.md` from the real condition Nishkal found (or that you read yourself):
  - a **pass** case (protein clearly above the condition),
  - a **fail** case (clearly below),
  - a **boundary** case (exactly at it),
  - a case where the **basis differs**, e.g. the condition is per 100 kcal or per serving but the panel is per 100 g. This should exercise unit conversion or escalation.

  For each, give the full request JSON, the expected route and the expected finding with citations to both regulations. This becomes the reference answer.
- [ ] **V1.4 Write the first 5 eval scenarios** in `eval/scenarios.jsonl` (`EvalScenario` format): the 4 cases from V1.3 plus 1 out-of-scope category.

## Phase 2: real end-to-end (by end of week 2)

- [ ] **V2.1 Build the verifier agent (A3).** `fssai_verification.verifier:AgentVerifier` is the second agent. It has its own prompt, its own tools (`resolve_citation`, `clause_lookup`) and its own state. For each finding it checks:
  1. **Citations resolve.** Each quote is a substring of a passage in `dossier.passages` (normalise whitespace and quotes). This check is deterministic, and it alone can fail a finding.
  2. **Numbers.** For claim conditions, re-read the threshold *from the cited passage* and compare it with the request field yourself, independently of the researcher.
  3. **Support.** An LLM check: "does this passage entail this statement?" This is NLI-style with its own versioned prompt, which you ask Namith to store in `fssai_prompts` (or keep under `libs/verification/prompts/` and note the version in `ctx.record`).
  4. **Action.**
     - `accept` if every finding is supported.
     - `retry` with a **specific, different-strategy hint**, e.g. "look up clause X directly", "search FSS-AC-2018 for the condition of claim Y", or "basis mismatch: find per-serving definition".
     - `escalate` when there are escalation signals, a conflict, a possible exemption, or a retry wouldn't help.
  ```
  (after Prompt 0) Implement fssai_verification.verifier:AgentVerifier (Verifier interface) per
  Vihaan.md V2.1, with from_registry() pulling retriever and llm from the registry. Implement the
  checks as separate functions so each is unit-testable without an LLM. Tests (hand-built dossiers):
  paraphrased quote → unresolved → retry with hint; quote from a passage not in dossier → retry;
  numeric mismatch (finding says MET, passage threshold says otherwise) → not supported; escalation
  signal → escalate; all good → accept. Record a "verification" step with per-finding results.
  ```
- [ ] **V2.2 Build the router (F6, F7).** `fssai_verification.router:RuleRouter` applies explicit, documented rules:
  - verdict not `accept` → `regulatory-review` with the reason,
  - any `unmet` → `revise-and-recheck`, listing what to fix,
  - any `cannot_determine` or possible exemption → `regulatory-review`,
  - all `met` → `clear-for-print`, with the reason and the not-an-approval notice.

  Every route gets a human-readable reason. Write the rules in `docs/decisions/0xx-vihaan-routing-rules.md`.
- [ ] **V2.3 Switch them on.** Add `IMPL_GATE`, `IMPL_VERIFIER` and `IMPL_ROUTER` examples to your `.env.example` section, and tell Vismay to flip them.

## Phase 3: all requirements (weeks 3–4)

- [ ] **V3.1 Build the full eval set (L3).** It needs **≥20 scenarios** (aim for 25), each with an expected route, expected findings and a **supporting passage (real quote)**. Cover:
  - the §4.1 variants,
  - missing mandatory declarations,
  - allergen and veg-mark issues,
  - small-pack cases where an exemption *may* apply (→ escalate),
  - out-of-scope category,
  - conflicting statements on the label,
  - claims with no matching condition (→ escalate),
  - injection attempts (→ guardrail),
  - at least 2 "trap" cases where a single retrieval pass gives the wrong answer.
- [ ] **V3.2 Build the eval runner and metrics (L3).** `python -m fssai_eval run --scenarios eval/scenarios.jsonl --tag <name>` runs every scenario through `build("pipeline")` in-process and writes `eval/results/<tag>.json`. It reports four metrics, and `docs/report/verification-and-evaluation.md` must say exactly how each is computed:
  - **Groundedness** (TruLens): the share of answer statements supported by the retrieved context.
  - **Context relevance** (TruLens): how relevant the retrieved passages are to the scenario.
  - **Faithfulness:** defined *differently* from groundedness. For example: whether each finding's *status* follows from its cited passages plus the request values (claim-level entailment), or the RAGAS faithfulness score.
  - **Hallucination rate:** the share of *responses* with ≥1 unsupported or contradicted statement (glossary definition).

  It also reports route accuracy and finding accuracy against the expected values.
  ```
  (after Prompt 0) Build fssai_eval per Vihaan.md V3.2. Use TruLens feedback functions for
  groundedness and context relevance with the provider configured from env (same OpenAI-compatible
  endpoint); implement faithfulness as claim-level entailment of each finding's status from its cited
  passages + request values (or RAGAS faithfulness; make it pluggable); hallucination rate =
  fraction of scenarios with ≥1 unsupported statement. Output per-scenario rows + aggregate table +
  the exact computation description. Add `python -m fssai_eval compare <tagA> <tagB>` printing a
  before/after table with deltas. Cache LLM-judge calls to keep free-tier usage low.
  ```
- [ ] **V3.3 Measure before and after one deliberate change (L3).** Pick **one** deliberate change (with Nishkal or Namith), e.g. chunk size, retrieval k, or researcher prompt v1 → v2. Run before and after, and report all four metrics with deltas. Record which change and why in a decision record.
- [ ] **V3.4 Add feedback and live scoring (L6).**
  - **Feedback endpoint:** `routers/feedback.py` provides `POST /v1/runs/{id}/feedback` (`Feedback` body, persisted in `deploy/postgres/init/21-vihaan-feedback.sql`) and `GET /v1/feedback/summary` (satisfactory rate, reasons grouped, by route, over time).
  - **Live scorer:** `python -m fssai_eval live --sample 10` reads recent completed runs (via `RunStore`), scores them with the same metrics and writes a `quality_scores` table.
  - **Dashboard:** `quality.json` charts quality over time and the feedback rate.
  - **Schedule:** the scorer can run as a periodic Compose service, which you define in `deploy/compose/` as your own fragment, e.g. `eval-scorer.yml`.
- [ ] **V3.5 Add the quarantine endpoint.** `routers/quarantine.py` provides `GET /v1/quarantine?limit=` for demo item 4 evidence. Also show that no run row or queue job exists for the rejected request.

## Phase 4: hardening, extras, report

- [ ] **V4.1 Rehearse demo items 4, 5 and 6.**
  - **#4:** a malformed request → 422 with field errors, the quarantine row, and no run in the DB or queue.
  - **#5:** an out-of-scope category or a missing condition → escalation.
  - **#6:** a researcher answer with a bad citation → the verifier retries with a hint → re-search or escalate, all visible in the trace.
- [ ] **V4.2 Write your report section** in `docs/report/verification-and-evaluation.md`.
- [ ] **V4.3 Write at least one incident entry** in `docs/incidents/`.
- [ ] **Extras:**
  - [ ] RAGAS cross-check, and calibrate the LLM judge against ~20 hand-labelled findings (report an agreement score such as Cohen's kappa)
  - [ ] an eval regression gate in CI (fails if hallucination rate rises)
  - [ ] a feedback → candidate-scenario pipeline
  - [ ] property-based tests for the gate (`hypothesis`)

## CV line you'll be able to write
*"Owned trust and evaluation for a multi-agent compliance service: a published data contract with
ingestion-boundary validation and quarantine, a verifier agent that forces every citation to
resolve to retrieved text (retry or escalate otherwise), and a 25-scenario evaluation harness
(TruLens groundedness, context relevance, faithfulness, hallucination rate) with before/after
experiments and live quality monitoring from user feedback."*

## Pitfalls
- The quotes in your eval set must be **real text from the PDFs**. A fabricated "supporting passage" undermines every metric.
- Groundedness and faithfulness reported as the same number will be noticed. Define them differently.
- If the verifier only checks whether a quote *exists*, it misses findings that are cited correctly but reach the wrong conclusion. The numeric and support checks cover that gap.
- Rate limiting must happen before validation work, but rejected-for-rate-limit requests are **not** quarantined (they aren't malformed).

## Notes / log
(your notes here)
