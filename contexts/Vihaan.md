# Vihaan: Trust & Evaluation

> Your plan, checklist and LLM prompts. **Only you edit this file.** Tick boxes as you go, and add
> notes at the bottom. Read `contexts/LLM_Context.md` first.

## Next steps to 30 October (written by Vismay, 2026-10-26)

Everything is due by **Fri 30 Oct**. What was checked on your branch: you stayed in your own paths; on Python 3.11
the gate, verification and eval tests pass; with all 11 parts real, `check_gate`, `check_verifier`, `check_router`
and `check_pipeline` pass, and demos #4, #5 and #7 behave correctly; all 54 supporting quotes in
`eval/scenarios.jsonl` and the quote in your §4.1 test values are verbatim PDF text.

Do next, in this order:
1. **Open your PR (`main` ← `vihaan`) now.** Your branch shows 1 of 3 checks only because of one of Vismay's API tests,
   which hard-coded the list of routes and so failed once yours existed. The fix is in Vismay's next PR; once that
   is merged, re-run your PR's checks and they pass. Until your PR merges, none of your work is live: the gate,
   verifier, router, feedback and quarantine endpoints and the eval runner are all stand-ins on `main`.
2. **V3.3 before/after (L3), with Namith:** `researcher` 1.0.0 against 1.1.0 (or the change decision 205 settles on),
   all four metrics with deltas, the numbers in `docs/report/verification-and-evaluation.md`. It needs the Groq key
   and your runner on `main`; the same pair serves Namith's M3.2 comparison.
3. **V4.1** rehearse demos #4, #5 and #6. Settle the RDA question with Nishkal (your test values, "What changes when
   the team adopts an RDA").
4. Tick V0.1 (it is done).

**If this does not happen:** demos #4, #5 and #6 and requirements F2, F6, A3, D1, L3, L6 and the D7 rate limit are
missing from `main`, and the web client's feedback form and reviewer console stay hidden. Your PR is the biggest
single blocker in the team right now.

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
3. contracts/fssai_contracts/*.py  (schemas, interfaces, context, fakes, pipeline, registry, conformance)

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
- My package skeletons already exist (day-0 baseline): fill them in, keep their class names and
  signatures, and make each conformance test (fssai_contracts.conformance) pass, then delete its xfail marker.
- Git: I work only on my own branch `vihaan` (check `git branch --show-current`). Never commit or
  push to main or a teammate's branch, never force-push, never --no-verify, merge origin/main
  (never rebase). No Co-Authored-By/"Generated with" lines. Commit or push only when I ask.
Summarise my current task in 3 lines, then wait for my go.
```

---

## Start here: your day-0 baseline

Your packages already exist as **skeletons**: installable, tested, wired to the right `IMPL_*` names,
and empty. Vismay scaffolded them on 2026-10-24 so all four of us start from the same working base.
They are yours like everything else in your paths: change anything except a seam's class name and
method signatures, which other people's code and `.env` depend on.

| Package | What you fill in | Its contract test | Task |
|---|---|---|---|
| `libs/gate` | `fssai_gate.gate:RequestGate` | `check_gate` | V1.2 |
| `libs/verification` | `fssai_verification.verifier:AgentVerifier` | `check_verifier` | V2.1 |
| `libs/verification` | `fssai_verification.router:RuleRouter` | `check_router` | V2.2 |
| `eval` | `python -m fssai_eval run ...` (CLI options fixed) | CLI options test | V3.2 |

**How a skeleton tells you you're done.** Every skeleton method raises `NotImplementedError("<task>: ...")`.
Its test calls the shared check in `contracts/fssai_contracts/conformance.py`, marked
`xfail(raises=NotImplementedError, strict=True)`. That gives three states:

| `pytest libs/gate libs/verification eval -q` says | Meaning | Do |
|---|---|---|
| `xfailed` | not built yet | build it |
| `FAILED` with an `AssertionError` | built, but it breaks a contract edge (the message says which) | fix it |
| `FAILED` with `XPASS(strict)` | built and conforming | delete the `xfail` line: from now on it guards you |

**Switching on.** When a seam's contract test passes without its marker, set its `IMPL_*` variable in
your `.env`, run `pytest contracts -q` and a local run (LLM_Context §7) with it on, add it as a comment
in your `.env.example` section, and tell Vismay. Until then everyone else keeps using the fake.

Each package README lists its files and commands. `conformance.sample_request()` gives you a valid
§4.1-style request for your own tests.

---

## Phase 0: setup

- [x] **V0.1 Set up and prove the loop.** Clone the repo and run `python scripts/setup_dev.py vihaan` (CONTRIBUTING.md §2). Your package skeletons already exist (see *Start here*), so this is only:
  1. Check that setup ended with your tests showing `xfailed` and nothing `failed`.
  2. Read the three package READMEs and `fssai_contracts/conformance.py` (`check_gate`, `check_verifier`, `check_router`).
  3. Make one small commit of your own on `vihaan` (e.g. a dated line in *Notes / log* below), `git push`, and open your first PR (`main` ← `vihaan`), so you've done the whole loop once.

## Phase 1: Evaluation 1 items

- [x] **V1.1 Publish the data contract (F1, D1).** Write `docs/data-contract.md` covering:
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
- [x] **V1.2 Build the gate (F2, D1).** `fssai_gate.gate:RequestGate`:
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
- [x] **V1.3 Write the §4.1 test values.** Write `docs/eval1/section-4.1-test-values.md` from the real condition Nishkal found (or that you read yourself):
  - a **pass** case (protein clearly above the condition),
  - a **fail** case (clearly below),
  - a **boundary** case (exactly at it),
  - a case where the **basis differs**, e.g. the condition is per 100 kcal or per serving but the panel is per 100 g. This should exercise unit conversion or escalation.

  For each, give the full request JSON, the expected route and the expected finding with citations to both regulations. This becomes the reference answer.
- [x] **V1.4 Write the first 5 eval scenarios** in `eval/scenarios.jsonl` (`EvalScenario` format): the 4 cases from V1.3 plus 1 out-of-scope category.

## Phase 2: real end-to-end

- [x] **V2.1 Build the verifier agent (A3).** `fssai_verification.verifier:AgentVerifier` is the second agent. It has its own prompt, its own tools (`resolve_citation`, `clause_lookup`) and its own state. For each finding it checks:
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
- [x] **V2.2 Build the router (F6, F7).** `fssai_verification.router:RuleRouter` applies explicit, documented rules:
  - verdict not `accept` → `regulatory-review` with the reason,
  - any `unmet` → `revise-and-recheck`, listing what to fix,
  - any `cannot_determine` or possible exemption → `regulatory-review`,
  - all `met` → `clear-for-print`, with the reason and the not-an-approval notice.

  Every route gets a human-readable reason. Write the rules in `docs/decisions/2xx-vihaan-routing-rules.md`.
- [x] **V2.3 Switch them on.** Add `IMPL_GATE`, `IMPL_VERIFIER` and `IMPL_ROUTER` examples to your `.env.example` section, and tell Vismay to flip them.

## Phase 3: all requirements

- [x] **V3.1 Build the full eval set (L3).** It needs **≥20 scenarios** (aim for 25), each with an expected route, expected findings and a **supporting passage (real quote)**. Cover:
  - the §4.1 variants,
  - missing mandatory declarations,
  - allergen and veg-mark issues,
  - small-pack cases where an exemption *may* apply (→ escalate),
  - out-of-scope category,
  - conflicting statements on the label,
  - claims with no matching condition (→ escalate),
  - injection attempts (→ guardrail),
  - at least 2 "trap" cases where a single retrieval pass gives the wrong answer.
- [x] **V3.2 Build the eval runner and metrics (L3).** `python -m fssai_eval run --scenarios eval/scenarios.jsonl --tag <name>` runs every scenario through `build("pipeline")` in-process and writes `eval/results/<tag>.json`. It reports four metrics, and `docs/report/verification-and-evaluation.md` must say exactly how each is computed:
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
- [x] **V3.4 Add feedback and live scoring (L6).**
  - **Feedback endpoint:** `routers/feedback.py` provides `POST /v1/runs/{id}/feedback` (`Feedback` body, persisted in `deploy/postgres/init/21-vihaan-feedback.sql`) and `GET /v1/feedback/summary` (satisfactory rate, reasons grouped, by route, over time).
  - **Live scorer:** `python -m fssai_eval live --sample 10` reads recent completed runs (via `RunStore`), scores them with the same metrics and writes a `quality_scores` table.
  - **Dashboard:** `quality.json` charts quality over time and the feedback rate.
  - **Schedule:** the scorer can run as a periodic Compose service, which you define in `deploy/compose/` as your own fragment, e.g. `eval-scorer.yml`.
- [x] **V3.5 Add the quarantine endpoint.** `routers/quarantine.py` provides `GET /v1/quarantine?limit=` for demo item 4 evidence. Also show that no run row or queue job exists for the rejected request.

## Phase 4: hardening, extras, report

- [x] **V4.1 Rehearse demo items 4, 5 and 6.**
  - **#4:** a malformed request → 422 with field errors, the quarantine row, and no run in the DB or queue.
  - **#5:** an out-of-scope category or a missing condition → escalation.
  - **#6:** a researcher answer with a bad citation → the verifier retries with a hint → re-search or escalate, all visible in the trace.
- [x] **V4.2 Write your report section** in `docs/report/verification-and-evaluation.md`.
- [x] **V4.3 Write at least one incident entry** in `docs/incidents/`.
- [ ] **Extras:**
  - [ ] RAGAS cross-check, and calibrate the LLM judge against ~20 hand-labelled findings (report an agreement score such as Cohen's kappa)
  - [ ] an eval regression gate in CI (fails if hallucination rate rises)
  - [x] a feedback → candidate-scenario pipeline
  - [x] property-based tests for the gate (`hypothesis`)

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
- 2026-10-26 (Vismay): **everything in this file is now due by Fri 30 Oct** (the first review), not over five weeks; see LLM_Context §9. Do it all as fast as you can. Only the phase headings changed (the week numbers are gone).
- 2026-10-26 (Vismay): your GitHub collaborator invite is still pending, and you can't push until you accept it
  (github.com/VismayHS/FSSAI_Label_Compliance_Agent/invitations). Do that before V0.1.
- 2026-10-26 (Vihaan): setup on a fresh clone. `setup_dev.py` failed twice: the old `origin/vihaan` predates the
  skeletons, and `libs/observability` is missing from the script's runtime install list. Fixed by merging
  `origin/main` and installing by hand (incident 2026-10-26-vihaan-setup-script-missing-dependency). V0.1 steps 1–2
  done; step 3 (first commit, push, PR) is still to do. Accept the GitHub invite first.
- 2026-10-26 (Vihaan): built V1.1–V3.5 except V3.3, plus V4.2, V4.3 and two extras. Conformance markers removed for
  the gate, verifier and router; all three conform, and inside both pipelines (`check_pipeline` on
  `ReferencePipeline` and `LangGraphPipeline`). Tests: gate 83, verification 77, eval 55 (Postgres tests included);
  `pytest contracts` green.
  - Gate: the strict contract (unknown fields, numeric strings, NaN/Infinity rejected), XF-01..10, a Redis token
    bucket (fail open), Postgres/memory quarantine. Teammates' payloads (web example, API tests, load-test
    payloads) all pass it.
  - Verifier: citations resolve → numbers re-read from the cited passage → one LLM support check → retry hint or
    escalate. Router: rules R1–R9 (decision 201).
  - Eval: 30 scenarios; every quote checked verbatim against the built index by `eval/tools/check_scenarios.py`.
    Runner with reference/llm/trulens judges, compare, gate, live scorer, candidates, calibrate.
  - API routes `/v1/quarantine[/{id}]`, `POST /v1/runs/{id}/feedback`, `GET /v1/feedback/summary`; SQL 20/21/22;
    `quality.json`; `deploy/compose/eval-scorer.yml` (profile `quality`).
  - Rehearsed demos #4, #5 and #6 against a local API (inline, fakes, my seams on) and #6 in process: all evidence
    present (`eval/tools/demo_trust.py`).
- Open, needs others or a key:
  - **Vismay:** flip `IMPL_GATE`/`IMPL_VERIFIER`/`IMPL_ROUTER` in the switchboard; add
    `deploy/compose/eval-scorer.yml` to the root `include:` list; `services/api/tests/test_ops.py::test_every_router_module_is_mounted`
    asserts exactly `["health", "runs"]` and fails once my two routers land (change it to a subset check or add
    `feedback` and `quarantine`); `setup_dev.py` `RUNTIME` needs `libs/observability`;
    `contracts/tests/test_reference_pipeline.py::test_registry_defaults_build_a_working_pipeline` should clear every
    `IMPL_*`, not only `IMPL_PIPELINE`; CI step for the eval gate
    (`python -m fssai_eval run --tag ci && python -m fssai_eval gate --baseline <committed> --candidate ci`).
  - **Namith:** agree on researcher prompt 1.0.0 vs 1.1.0 as the V3.3 change (decision 205); the eval matches finding
    ids with a fuzzy match, but canonical ids help (eval/README.md).
  - **Team:** the protein RDA decision. Until then the §4.1 cases are `regulatory-review` (test values doc).
  - **Me:** an LLM key in `.env` for V3.3 and real eval numbers; Docker for the Postgres tests and the full-stack
    rehearsal (V4.1); hand-label ~20 items (`fssai_eval calibrate template`) for the kappa extra.
- 2026-10-26 (Vihaan): pre-push review.
  - Reproduced the CI `python` job in a clean `python:3.11-slim` container with a real Postgres: every package
    green except Vismay's exact-match router test (below).
  - Fixed what the review found:
    - an f-string that only compiles on Python 3.12+ (it would have broken CI and the worker image);
    - "Very low" claims checked against the Low condition;
    - "no/without added sugar" read as a Schedule I number;
    - numeric conditions read from labelling passages (now only from FSS-AC-2018);
    - R6 treated one checked claim as covering every claim (now per claim);
    - quarantine and feedback reads raised a 500 when Postgres was down (now a degraded read or an honest 503);
    - a wasted LLM call on runs that escalate anyway.
  - Added Postgres tests for feedback, live scores, candidates and every quality-dashboard query; built and ran
    the `eval-scorer` image.
- 2026-10-26 (Vihaan): merged `origin/main` (no conflicts). On Python 3.13 with a real Postgres, every package's
  tests pass, including `services/api`, now that Vismay's router test is fixed; `audit_secrets.py` is clean.
  Pushed, and opened **PR #9** (`main` ← `vihaan`), which closes V0.1.
- 2026-10-26 (Vihaan): V4.1 rehearsed on the full Compose stack. The configuration is `main`'s `.env.example`
  (real retriever, LangGraph researcher, guardrails, classifier) plus my gate, verifier and router; the LLM is
  still the fake, since there is no key yet. `smoke.py` passes. `eval/tools/demo_trust.py --api ... --in-process`
  showed all evidence:
  - #4: 422, quarantine row, no run, rejected counter +1.
  - #5: out-of-scope and no-condition claims both go to `regulatory-review` with a reason.
  - #6: the verifier's steps are in the trace; in process, a bad quote is retried with a hint, then verified.

  To redo on demo day with the Groq key: on the fake LLM the researcher cannot draft findings, so #5's claim cases
  escalate as "could not be drafted" rather than for the RDA.
- 2026-10-26 (Vihaan): V3.3 prep. `fssai_eval run --pause-s N --resume` paces scenarios for Groq's 8k tokens/min,
  writes results after every scenario, marks provider failures (429/outage) as `provider_failed` (counted, not
  scored), and reruns only those. Still waiting on two things: Namith's researcher fix on `main`, and my Groq key
  in `.env`. Decision 205 has the commands.
- Open: the RDA decision with Nishkal (his file still lists it as open). Until it is settled, §4.1 stays
  `cannot_determine` → `regulatory-review` (test values doc, "What changes when the team adopts an RDA").

