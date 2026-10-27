# LLM_Context.md: FSSAI Label Compliance Agent

> **The project's stable context.** Give this file to your LLM at the start of every session,
> together with your own file (`docs/contexts/<YourName>.md`) and the `packages/contracts/` folder.
> This file changes rarely and only through Vismay. Your progress and checklists go in your
> own file, never here.

**Reading order (people and LLMs):**
1. This file
2. Your own `docs/contexts/<Name>.md`
3. `packages/contracts/fssai_contracts/`: `schemas.py`, `interfaces.py`, `context.py`, `fakes.py`, `pipeline.py`, `registry.py`, `conformance.py`
4. [`CONTRIBUTING.md`](../../CONTRIBUTING.md) before your first commit: one branch per person, PRs into `main`
5. [`tools/skills/project/fssai-workflow/SKILL.md`](../../tools/skills/project/fssai-workflow/SKILL.md) before writing code: how every change is built, tested and reviewed ([`tools/skills/README.md`](../../tools/skills/README.md) lists all skills)

The original course documents are in `docs/course/`:
- `MiniProject_10_Food_Label_Compliance.pdf`: the spec
- `00_GLOSSARY.pdf`: official definitions, summarised in §13
- `00_INDEX.pdf`: all 15 course projects

---

## 1. Team

| Person | Git branch | Workstream | Units touched | One line |
|---|---|---|---|---|
| **Nishkal** | `nishkal` | Knowledge & Performance | 1, 2, 3 | Corpus, index, retrieval, caching, observability stack, SLO + load test |
| **Namith** | `namith` | Agent Reasoning | 3, 4 | Classifier + research agent, LangGraph graph, prompts, guardrails, agent metrics |
| **Vihaan** | `vihaan` | Trust & Evaluation | 1, 3, 4 | Data contract + gate, verifier agent + routing, eval set + metrics, feedback |
| **Vismay** | `vismay` | Platform & Integration (+ frontend) | 1, 2, 4 | API, queue, worker, LLM gateway + reliability, cost, Compose, tracing, web client |

Each person commits and pushes **only to their own branch**. Nobody works on `main` (§8.2).

- **Repo:** https://github.com/VismayHS/FSSAI_Label_Compliance_Agent (owner: Vismay, GitHub `VismayHS`)
- **Course:** UE24AM342AA5, ML System Design & AgentOps, Dept of CSE (AI & ML), PESU. Mini Project 10, Jackfruit (Level 3).
- **Team size:** the course says 2–3 students per team; we are 4. Confirmed with the instructor (2026-10-25).
- **Goal:** all 22 requirements and all 10 demo items, plus the extras in §11. We want a project good enough to put on a CV, not just enough to pass.

Each workstream deliberately covers several course units, so every person learns part of the
agent, the LLMOps side and the platform, and can answer viva questions about all three.

---

## 2. The project on one page

We are building a **multi-agent service**. It takes a proposed packaged-food label (as text) plus
the package specification and checks them against two FSSAI regulations. It returns a
**compliance finding for each requirement, with citations to regulation and clause**, and routes
the label to one of:
- `clear-for-print`
- `revise-and-recheck`
- `regulatory-review`

The system **never approves a label**; a regulatory affairs professional decides.

**Why it's hard.** The requirements live in two regulations that don't refer to each other:

- **FSSAI Labelling & Display Regulations, 2020** (`FSS-LD-2020` in our code): what must appear on the label.
- **FSSAI Advertising & Claims Regulations, 2018** (`FSS-AC-2018`): the conditions any claim must meet.

Printing "source of protein" on a pack triggers a condition in the Claims regulation, but the
Labelling regulation never points there. The course index names this as our project's obstacle:
*"A claim condition in a different regulation from the labelling rules."*
A single embedding search won't find it, because the request never mentions the provision that
decides the outcome.

**The case we're tested on live (§4.1 of the spec):**
> *"The label carries the claim 'source of protein'. Is the claim permitted, given the protein
> content declared on the nutrition panel?"*

The system must:
1. find the condition in the Claims regulation,
2. compare it with the declared protein value, and
3. cite **both** regulations.

At Evaluation 1 we show the exact passages and test values. Once confirmed, they become the
reference answer for the demo.

**The required agent loop (spec §5):**
1. Retrieve the provision that appears to apply.
2. **Check whether another provision modifies it, and search for it.**
3. Search again with a query derived from what was just read.
4. **Verify that the retrieved passages support the answer.**
5. If they don't, retry with a different strategy or escalate.

Steps 2 and 4 are what make it an agent rather than a fixed pipeline, and both are assessed.

**What's hardest (and graded hardest):**
- **F5:** findings grounded in retrieved text.
- **F7:** knowing when *not* to answer.

**Escalating is always better than inventing.** The glossary says *"stating a provision that does
not exist is more serious than declining to answer."*

**Hard rule:** if `docker compose up` from a clean clone doesn't start and serve a valid request
at the demo, we get **zero marks**. `main` must always boot.

---

## 3. Requirements → owners

Every requirement has one primary owner. "+" marks a contributor. The F-requirements are this
project's own; the A, L and D requirements are shared by all 15 course projects.

| ID | Requirement (short) | Owner |
|---|---|---|
| F1 | REST interface + published data contract | Vihaan (contract) + Vismay (endpoint) |
| F2 | Schema/range/category/cross-field validation at ingestion; quarantine rejects | Vihaan |
| F3 | Classify product category; detect claims | Namith |
| F4 | Retrieve applicable labelling requirements + each claim's condition | Namith + Nishkal (retrieval) |
| F5 | Finding per requirement, grounded, cited to regulation + clause | Namith (+ Vihaan verifies) |
| F6 | Route to clear / revise / regulatory-review with reason | Vihaan |
| F7 | Escalate on conflict, possible exemption, out-of-corpus category | Vihaan (+ Namith raises signals) |
| F8 | Health, metrics, structured logs for the whole pipeline | Vismay (+ every service exposes them) |
| A1 | LangGraph agent; retrieval as a *tool*; ≥3 tools; loop bounded by steps/tools/time | Namith (+ Nishkal tool backends) |
| A2 | ≥2 agents, distinct roles, defined hand-off; topology + mid-run failure documented | Namith (+ Vihaan's verifier is agent #2) |
| A3 | Verify every answer against retrieved passages; citations must resolve; else retry/escalate | Vihaan |
| A4 | FastAPI, async runs (run id + polling), queue between submit and execute | Vismay |
| A5 | Timeouts, bounded retry + backoff, circuit breaker, graceful degradation | Vismay |
| A6 | Per-agent dashboard: success rate, steps/tool calls, latency, retry rate, uptime | Namith |
| A7 | `--scale worker=3` works; measure throughput/p95; find bottleneck | Nishkal (+ Vismay keeps worker stateless) |
| A8 | Simple web client: submit, poll, show route + citations + escalation | Vismay |
| L1 | LangChain/LlamaIndex + FAISS/Chroma; chunking strategy; partial re-embed | Nishkal |
| L2 | Versioned prompts; version on every response; compare ≥2 variants | Namith (+ Vihaan's runner) |
| L3 | ≥20-scenario eval set incl. §4.1; TruLens; 4 metrics; before/after one change | Vihaan |
| L4 | Prompt-injection defence, output filtering, toxicity in + out | Namith |
| L5 | Tokens + cost at call time, per step and per run; cost/100 runs; biggest driver | Vismay |
| L6 | Feedback endpoint (persisted, aggregated); auto-score live sample; quality chart | Vihaan |
| D1 | Data contract for every external interface; validate before any agent; quarantine | Vihaan |
| D2 | Idempotent CLI pipeline (parse → chunk → embed → index); freshness + throughput metrics | Nishkal |
| D3 | ≥4 Compose services, one `docker compose up`, health checks; justify boundaries | Vismay |
| D4 | No credentials/endpoints/model ids in repo; `.env.example` | Vismay (everyone obeys) |
| D5 | Structured logs, correlation id, OTel → Jaeger, Prometheus, Grafana, run reconstruction | Vismay (correlation, reconstruction) + Nishkal (metrics, tracing backend, dashboards) |
| D6 | p95 SLO declared *before* measuring; Locust + stub LLM; failure concurrency | Nishkal |
| D7 | Caching (justified, measured) + per-client rate limiting | Nishkal (cache) + Vihaan (rate limit) |
| D8 | Runbook for top 2 failure modes + incident log with real entries | Namith (runbook) + **everyone** (incidents) |

---

## 4. Architecture

```
 browser ── web client (A8) ──┐
                              ▼
                    ┌───────────────────┐  X-Client-Id, X-Correlation-Id
                    │  api  (FastAPI)   │  gate: rate limit → validate → quarantine (D1/F2/D7)
                    │                   │  202 {run_id} immediately (A4)
                    └───────┬───────────┘
                            │ enqueue (Redis)
                            ▼
                    ┌───────────────────┐  build("pipeline").run(request, ctx)
                    │ worker  (x N, A7) │  guardrails → classifier → [researcher ⇄ verifier]×≤3
                    └───┬──────┬────────┘   → router → output filter
                        │      │ LLMClient (gateway: timeouts, retry, breaker, cost)
          FAISS index ◄─┘      └──► LLM provider (free tier)  |  stub-llm for load tests (D6)
          (built by indexer job, D2)

 redis:    queue · retrieval cache · rate-limit counters · breaker state
 postgres: runs + step traces (D5) · quarantine (D1) · feedback + quality scores (L6)
 observability: prometheus · grafana · jaeger · cadvisor
```

**Compose services (D3 needs ≥4):** `api`, `worker` (scalable), `redis`, `postgres`, `indexer`
(one-shot job), `prometheus`, `grafana`, `jaeger`, `cadvisor`, `web`, and `stub-llm` (load tests only).

**Agent topology (A2).** Three agents, each a separate LangGraph subgraph with its own prompt,
tools and state. They communicate **only** through the hand-off schemas:

| Agent | Owner | Input → Output | Tools |
|---|---|---|---|
| Classifier | Namith | `LabelCheckRequest` → `Classification` | request field lookup |
| Researcher | Namith | `Classification` → `ResearchDossier` | `corpus_search`, `clause_lookup`, `request_field_lookup` |
| Verifier | Vihaan | `ResearchDossier` → `Verdict` | `resolve_citation`, `clause_lookup` |

The router (Vihaan) and guardrails (Namith) are deterministic steps around them. Namith documents
what happens if any of them fails mid-run.

**Stack.** Defaults; change one only with a decision record (§8.6):

| Area | Default |
|---|---|
| Language | Python 3.11 |
| Agents | LangGraph |
| Retrieval | LangChain + FAISS, `sentence-transformers` run locally (small model, e.g. MiniLM-class) |
| API + validation | FastAPI, Pydantic v2 |
| Queue | Redis + RQ, in-process `SimpleWorker`s (decision 302) |
| Web client | React + Vite + TypeScript, CSS tokens, React Bits for run-state motion (decision 303) |
| Storage | Postgres |
| Evaluation | TruLens |
| Observability | OpenTelemetry → Jaeger, Prometheus, Grafana, cAdvisor |
| Load testing | Locust |
| Deployment | Docker Compose |

**LLM provider:** any free tier with an **OpenAI-compatible** endpoint (e.g. Groq, Google AI
Studio, OpenRouter's free models). The base URL, key and model id live **only** in `.env`. Set a
spending limit on the account.

**We use Groq's free tier.** It allows **8,000 tokens per minute per model** and 1,000 requests a day (read from its
response headers), and one real run uses about 8,000 to 12,500 tokens. So run real-LLM checks **one at a time, about
a minute apart**, and plan the eval set as at least half an hour per prompt variant. The fallback model has its own
token budget. Load tests always use the stub LLM. See incident `2026-10-26-vismay-groq-free-tier-rate-limit`.

**Out of scope:** model training, cloud deployment, and images (labels arrive as text only).

---

## 5. Repo layout and who owns which path

**You only edit paths you own.** That rule is what keeps merge conflicts close to zero.

**Layout since 27 Oct 2026** ([decision 305](../decisions/305-vismay-repository-layout.md)): `apps/` (what runs),
`packages/` (Python components, incl. `contracts/` and `eval/`), `infra/` (Compose, Postgres, observability, load test),
`data/corpus/`, `docs/` (incl. `contexts/`) and `tools/` (scripts, skills). Older notes may use the earlier paths:
`services/` is now `apps/`, `libs/` is `packages/`, `deploy/` is `infra/`, and `contracts/ eval/ corpus/ contexts/
scripts/ skills/ observability/ loadtest/` moved under those. After pulling it, re-run `python tools/scripts/setup_dev.py <name>` once.

| Path | Owner | What |
|---|---|---|
| `packages/contracts/` | shared, steward Vismay | Schemas, interfaces, fakes, reference pipeline, registry (§6) |
| `docs/contexts/LLM_Context.md` | Vismay | This file |
| `docs/contexts/<Name>.md` | that person | Your plan, checklist, prompts, notes |
| `docs/course/*.pdf` | none | Course documents. Never edit. |
| `docs/eval1/` | Nishkal (`*-passages.md`), Vihaan (`*-test-values.md`), Vismay (`project-plan.md`) | Evaluation 1 deliverables |
| `docs/decisions/` | author of each file | Decision records (ADRs), one file each: `NNN-<name>-<slug>.md`. Number blocks so parallel branches never clash: Nishkal `001–099`, Namith `100–199`, Vihaan `200–299`, Vismay `300–399`; take the next free number in your block. Index: `docs/decisions/README.md` |
| `docs/incidents/` | author of each file | Incident log (D8), one file each: `YYYY-MM-DD-<name>-<slug>.md` |
| `docs/runbook.md` | Namith | D8 runbook |
| `docs/data-contract.md` | Vihaan | D1/F1 published contract |
| `docs/agent-topology.md` | Namith | A2 |
| `docs/architecture.md` | Vismay | Diagram with deployment boundaries |
| `docs/report/<section>.md` | each section's owner (§10) | Report sections; Vismay assembles |
| `data/corpus/` | Nishkal | Regulation PDFs + `manifest.json` (versions, sha256, source URL) |
| `packages/ingest/` | Nishkal | `fssai_ingest`: CLI index builder (D2) |
| `packages/retrieval/` | Nishkal | `fssai_retrieval`: FAISS retriever + cache |
| `packages/observability/` | Nishkal | `fssai_observability`: JSON logs, OTel init, metric helpers |
| `apps/stub_llm/` | Nishkal | OpenAI-compatible stub provider (D6) |
| `infra/loadtest/` | Nishkal | `SLO.md`, `locustfile.py`, results |
| `infra/observability/prometheus/`, `infra/observability/grafana/provisioning/` | Nishkal | Scrape config, datasources |
| `infra/observability/grafana/dashboards/<file>.json` | per file: `service-overview` Nishkal, `agents` Namith, `quality` Vihaan, `cost` Vismay | One dashboard each |
| `packages/agents/` | Namith | `fssai_agents`: classifier, researcher, LangGraph pipeline, tools |
| `packages/prompts/` | Namith | `fssai_prompts`: versioned prompt files + store |
| `packages/guardrails/` | Namith | `fssai_guardrails` |
| `packages/gate/` | Vihaan | `fssai_gate`: validation, quarantine, rate limit |
| `packages/verification/` | Vihaan | `fssai_verification`: verifier agent + router |
| `packages/eval/` | Vihaan | `scenarios.jsonl`, runner CLI, live scorer, results |
| `apps/api/app/routers/feedback.py`, `quarantine.py` | Vihaan | Their HTTP routes (auto-mounted by the API) |
| `apps/api/` (everything else) | Vismay | FastAPI app |
| `apps/worker/` | Vismay | Queue consumer |
| `apps/web/` | Vismay | A8 web client |
| `packages/llm_gateway/` | Vismay | `fssai_llm_gateway`: provider adapter, resilience, cost |
| `packages/run_store/` | Vismay | `fssai_run_store`: Postgres `RunStore` (runs + step traces) |
| `docker-compose.yml` (root) | Vismay | Only an `include:` list of fragments |
| `infra/compose/<service>.yml` | that service's owner | Your services' Compose definitions |
| `infra/postgres/init/NN-<name>-<table>.sql` | author | Your own tables |
| `.env.example` | everyone, **own section only** | Pre-split into one section per owner |
| `README.md`, `Makefile`, `.github/` | Vismay | |
| `CONTRIBUTING.md`, `.githooks/`, `tools/scripts/setup_dev.py` | Vismay | Branch workflow, the git hooks that enforce it, one-time clone setup |
| `tools/skills/`, `tools/scripts/sync_skills.py` | Vismay (propose changes in a PR) | Shared AI-assistant skills: our `project/` skills plus pinned `vendor/` copies of taste-skill, Emil's skills, impeccable, React Bits, ponytail, ECC, ruflo. Read by everyone; see `tools/skills/README.md` |
| `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` | Vismay | Instructions every AI coding assistant loads (`CLAUDE.md` imports `AGENTS.md` + this file); shared Claude Code settings (attribution off) |

**Day-0 baseline.** Every Python package in this table already exists as a tested skeleton (Vismay,
2026-10-24): the seam classes under the names `.env.example` switches to, each method raising
`NotImplementedError("<task>: ...")`, and a conformance test marked `xfail` until it is built. A
skeleton belongs to its path owner like the rest of their paths. See *Start here* in each `docs/contexts/<Name>.md`.

Each `packages/*` and `apps/*` folder is its own Python package with its **own `pyproject.toml`**,
which lists only its own dependencies. There is no shared requirements file to fight over.

---

## 6. Shared contracts: how nobody waits for anybody

`packages/contracts/fssai_contracts/` was committed on day 0 and already works end to end.

- **`schemas.py`**: every shape passed between modules or over HTTP. Includes:
  - `LabelCheckRequest`, `GateDecision`, `Passage`, `Classification`, `Finding`, `Citation`
  - `ResearchDossier`, `Verdict`, `Routing`, `RunResult`, `StepRecord`
  - `Feedback`, `EvalScenario`, …
- **`interfaces.py`**: one `Protocol` per seam, with the owner noted:
  - `RequestGate`, `Retriever`, `LLMClient`, `PromptStore`, `Guardrails`, `Classifier`
  - `Researcher`, `Verifier`, `Router`, `Pipeline`, `RunStore`
- **`fakes.py`**: a working fake for every seam. Its regulation text is labelled PLACEHOLDER. It is **not** real FSSAI text.
- **`pipeline.py`**: `ReferencePipeline`, the agreed hand-off order and its edge behaviour, written as plain Python. Namith's LangGraph pipeline replaces it and must pass the same tests.
- **`context.py`**: `RunContext`, carried through every call. It provides:
  - loop bounds via `check_budget()` (A1)
  - the step trace via `record()` (D5, L5)
  - structured events via `event()`
- **`registry.py`**: the switchboard. `IMPL_<SEAM>=module:Class` in `.env` picks the real implementation; if the variable is empty, the fake is used.
- **`dev_llm.py`**: a bare OpenAI-compatible client, so agent work can use a real LLM before Vismay's gateway exists.
- **`conformance.py`**: one `check_<seam>(impl)` per seam (gate, retriever, prompts, guardrails, classifier, researcher, verifier, router, pipeline, run store). It tests the edges everyone else relies on: shapes, recording rules, verbatim citations, never upgrading a route, escalation on injection, scope and budget. Plus `sample_request()` for your own tests. The fakes pass every check (`packages/contracts/tests/test_conformance.py`).

**How to use them:**

1. **Code against the interface, never against a teammate's class.**
2. **Develop and test against the fakes.** Your tests must not need anyone else's unfinished code.
   Your seam's `conformance.check_<seam>` must pass before you switch it on.
3. **Integrate by flipping a switch.** When your implementation is ready, set
   `IMPL_RETRIEVER=fssai_retrieval.faiss:FaissRetriever` (for example) in `.env`. No one else
   edits code to pick it up.
4. **Recording rules.**
   - LLM clients record their own `llm` steps (they know tokens and cost).
   - The agent records a `tool` step for every tool call, **including the full passages returned**, so any run can be reconstructed (D5).
   - Call `ctx.check_budget()` before each step.
5. **Prompt tag convention.** Every system prompt starts with `[prompt:<name>@<version>]`. The stub
   LLM picks its canned reply by this tag, and it makes traces easy to read.
6. **Changing a contract.**
   - Only **additive** changes: new *optional* fields, new enum members, new fakes. Anyone may make one.
   - Make each change its own commit titled `contracts: ...` on your own branch, and open the PR to `main` right after it (before piling other work on top), so the reviewer sees just that change. It needs one affected owner's approval and an announcement in the group chat.
   - Renames and removals need everyone affected to agree.
   - `pytest packages/contracts` must still pass.

Run the contract tests:
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows PowerShell   (macOS/Linux: source .venv/bin/activate)
pip install -e "packages/contracts[test]"
pytest packages/contracts -q        # §4.1 pass/fail, out-of-scope, injection, retry→escalate, budget, outage, gate, registry + conformance kit
```

---

## 7. HTTP API contract

The owner is Vismay unless noted. The request and response bodies are the Pydantic models in
`schemas.py`, and FastAPI publishes them as OpenAPI at `/docs`.

| Method + path | Body / headers | Returns |
|---|---|---|
| `POST /v1/runs` | `LabelCheckRequest`; header `X-Client-Id` (required), `X-Correlation-Id`, `X-Callback-Url` (optional) | `202 {run_id, status_url, trace_url, correlation_id}` + `Location` · `400` bad/missing client id or a callback host not allowed · `413` body over `API_MAX_REQUEST_BYTES` · `422 {errors[], quarantine_id}` · `429 {retry_after_s}` + `Retry-After` · `503` queue down |
| `GET /v1/runs?limit=` | | Recent runs, newest first: id, state, product name, route |
| `GET /v1/runs/{run_id}` | | `RunStatus`: state, the accepted `request`, `correlation_id`, and the `result` when done |
| `GET /v1/runs/{run_id}/trace` | | Full reconstruction (D5): the request, every step in order with inputs and outputs (queries, full passages, LLM messages and text), prompt versions, per-step and per-agent latency, tokens and cost, queue wait, verdict, route |
| `POST /v1/runs/{run_id}/feedback` | `{satisfactory, reason}` | `201` (Vihaan) |
| `GET /v1/feedback/summary` | | Aggregates (Vihaan) |
| `GET /v1/quarantine?limit=` | | Rejected records with field-level errors (Vihaan) |
| `GET /healthz` · `GET /readyz` · `GET /metrics` | | On **every** HTTP service: liveness, dependency readiness, Prometheus metrics |

- Run ids are 32-character hex. Every response carries `X-Correlation-Id` (the caller's, if it is a
  safe 1–128 character id, otherwise a new one); the same id is on the run, its job, every step and
  every log line.
- Submission order: client id → size limit → gate (rate limit, validate, quarantine) → save `queued`
  → enqueue. A reject never creates a run or a job (D1, demo #4). Non-JSON bodies are quarantined too.
- `X-Callback-Url` (extra): when the run ends, the worker POSTs `{event: "run.finished", run_id, state, route, complete,
  status_url, trace_url}` to it, signed with `WEBHOOK_SECRET` (`X-FSSAI-Signature`). Off unless the host is in
  `WEBHOOK_ALLOWED_HOSTS`; a failed callback never changes the run.
- Runs are executed per `RUN_DISPATCH` (decision 302): `queue` (RQ on Redis, `python -m fssai_worker`)
  in Compose, `inline` (a thread pool in the API) for local development.

**Adding routes.** The API mounts every `router` it finds in `apps/api/app/routers/*.py`
automatically, so Vihaan's routes appear without anyone editing `main.py`. A router reaches the
shared services through `request.app.state`: `gate` (the `RequestGate`, e.g. its quarantine),
`run_store` (the `RunStore`), `dispatcher` and `settings`. Call blocking code with
`fastapi.concurrency.run_in_threadpool`.

Run the whole stack (queue mode, Postgres run store, every service), from the repo root:

```bash
cp .env.example .env                 # once; then set your own section
docker compose up -d --build         # web :8080 · API + /docs :8000 · Grafana :3000 · Prometheus :9090 · Jaeger :16686
python tools/scripts/smoke.py              # demo #1: ready, one run to completion, one reject that starts no run
```

Or the API alone without Docker (inline mode, fakes by default):

```bash
<venv-python> -m uvicorn app.main:create_app --factory --env-file .env --port 8000   # docs at /docs
```

`GET /v1/runs/{run_id}/trace` also returns `jaeger_url`, this run's spans in Jaeger, when tracing is on.

---

## 8. How we work: async, own pace, no blocking

### 8.1 The five rules
1. **Own your paths** (§5). If you need something changed in someone else's path, message them
   or open a GitHub issue. Keep working around it with a fake in the meantime.
2. **You are never blocked.** Every task in every personal file can be built and tested with the
   fakes. If a fake isn't good enough, improve it with a `contracts:` PR. Don't wait.
3. **Your branch is yours; `main` belongs to nobody.** Commit and push to *your own branch*
   (`nishkal`, `namith`, `vihaan`, `vismay`) as often as you like, since that affects nobody. Work
   reaches `main` only through a PR whose CI checks pass; open one whenever work is finished (no daily limit).
4. **`main` always boots.** Once Compose exists, `make smoke` must pass before you merge.
5. **Write it down.** Decisions go in `docs/decisions/`, failures in `docs/incidents/`, and
   progress in your own `docs/contexts/<Name>.md` checklist.

### 8.2 Git workflow: one branch per person
The full guide is [`CONTRIBUTING.md`](../../CONTRIBUTING.md). In short:

| Branch | Who pushes | What |
|---|---|---|
| `nishkal` · `namith` · `vihaan` · `vismay` | only that person | Your own long-lived branch and your complete commit history, from day 1 to submission |
| `main` | **nobody**; it changes only when a PR is merged | The integrated system; always boots; what we demo and submit |

```bash
python tools/scripts/setup_dev.py <name>                   # once per clone: own branch, hooks, .venv, tests, .env
git switch <name> && git pull                        # start of a session
git fetch origin && git merge origin/main            # bring in teammates' merged work (merge, never rebase)
# ... work, commit often ...
pytest packages/contracts -q && pytest <your-package> -q      # (+ make smoke once compose exists)
git push                                             # always to origin/<name>, never anywhere else
# open a PR on GitHub: base main ← <name>, merged with "Create a merge commit"
```
- **Never** push to `main`, push to a teammate's branch, force-push, rewrite pushed history, delete a branch, or bypass the hooks with `--no-verify`. The hooks in `.githooks/` block these.
- PRs are merged with a **merge commit** (squash and rebase are off), so every commit keeps its author and `git log --author=<you>` shows your work. Keep using the same branch after the merge.
- If your PR touches only your own paths and the checks pass, you can merge it yourself. PRs touching `packages/contracts/`, `docker-compose.yml`, `.env.example` structure or `.github/` need one approval.
- Need a teammate's unmerged work? Use the fake. Don't merge their branch into yours; read it with `git diff main...origin/<their-branch>`.
- **Commits are yours alone:** no `Co-Authored-By:` trailers for AI tools and no "Generated with ..." lines. The `commit-msg` hook strips them.
- Commit messages: `<area>: <what changed>`, e.g. `retrieval: add clause lookup by id`, `contracts: add Passage.page`.

### 8.3 Files everyone touches, made conflict-free
- **`.env.example`:** already split into one section per owner. Edit only your own section.
- **Compose:** the root `docker-compose.yml` only `include:`s fragments. Each owner edits their own `infra/compose/*.yml`.
- **Grafana:** one dashboard JSON file per owner.
- **Postgres:** one init SQL file per owner and table.
- **Logs and records:** incidents and decision records are one file each, so no shared log file ever gets edited.
- **Report:** one section file per owner.

### 8.4 Async standup (group chat, any time of day, ~2 lines)
```
[Name] done: … | next: … | needs from others (not blocking): … | contract change? y/n
```
A 30-minute weekly call is optional and handy for flipping the `IMPL_*` switches together and
running the full stack. If you can't make it, catch up in the chat.

### 8.5 Definition of done (any task)
- The code is in your own paths, and its tests pass with fakes **and** with real implementations once those exist.
- A seam implementation passes its `conformance.check_<seam>` test with the `xfail` marker removed.
- Steps go through `ctx.record()`. Events go through `ctx.event()`. Metrics are exposed if relevant.
- Any new config is env-only and added to your section of `.env.example` with a comment.
- The task is ticked in your `docs/contexts/<Name>.md`, and the decision is recorded in `docs/decisions/` if you made one.

### 8.6 Decision records (ADRs)
Keep them short: context, options considered, decision, consequences. The report asks for *"design
decisions and what was rejected"*, and these files are where that comes from.

### 8.7 Incident log (D8)
Whenever something really breaks during development, write `docs/incidents/YYYY-MM-DD-<name>-<slug>.md`
covering what happened, how you noticed, the cause, the fix and the lesson. Each person aims for
**at least one** genuine entry. They're also good material for the viva.

### 8.8 Mixed team: Windows + macOS
We develop on both. Everything runs in Linux containers, so most differences disappear, but not all:

- **Docker Desktop** on both (WSL 2 backend on Windows). Give it **at least 6–8 GB RAM**, because local embeddings plus the full stack are heavy. Compose v2.20+ is needed for `include:`.
- **Python 3.11+** locally:
  - macOS: install from python.org or `brew install python@3.11`. Don't use the system Python.
  - Windows: install from python.org, then use `py -3.11`.
- **venv activation:**
  - macOS: `source .venv/bin/activate`
  - Windows PowerShell: `.venv\Scripts\Activate.ps1`
- **Line endings:** `.gitattributes` forces LF. Never commit CRLF, and don't turn on `core.autocrlf` overrides.
- **Apple Silicon (ARM) Macs:**
  - Only use images and wheels that ship `arm64` builds. Python slim, Redis, Postgres, Prometheus, Grafana and Jaeger all do, and so do `faiss-cpu`, `torch` and `sentence-transformers`.
  - **Never pin `platform: linux/amd64`** in Compose. If something only ships for amd64, raise it in the chat before using it.
  - A teammate on each OS runs `make smoke`, or the plain `docker compose` equivalent, at least once a week.
- **Scripts:** write helpers in Python, not bash, so they work on Windows. `make` exists on macOS but not on Windows, so every `make` target must be a thin wrapper over a command that also works when typed by hand.
- **File names:** macOS and Windows treat file names as case-insensitive. Never create two files whose names differ only by case, and keep imports matching file names exactly, because the Linux containers are case-sensitive.
- **Paths:** in Python, always use `pathlib`. Never hard-code `/` or `\` separators or absolute paths.

---

## 9. Phases and milestones

**Deadline: everything is due by Friday 30 October 2026, the first review (Evaluation 1).** The team decided on
2026-10-26 to finish the **whole project** by then: every task in every personal file, all 22 requirements, all 10 demo
items, the report sections and the rehearsals. There are no intermediate deadlines. Finish as fast as you can; finishing
early is better. The phases below are only the order of work, because each one builds on the one before.

| Phase | Team milestone (everyone's personal file breaks this down) |
|---|---|
| **0. Setup** | Everyone has cloned the repo, run `tools/scripts/setup_dev.py <name>` (own branch, hooks, `pytest packages/contracts`, own package skeletons installed), and merged a first small PR from their own branch into `main`. Product category chosen (decision record 001). |
| **1. Evaluation 1 items** | Corpus confirmed; §4.1 passages and test values written up; data contract v1; **SLO declared and committed**; walking skeleton (`compose up` → submit → fake pipeline → result); project plan. |
| **2. Real end-to-end** | Real index, retriever, LangGraph researcher, verifier, router and LLM gateway switched in with `IMPL_*`. The §4.1 case runs on the real stack. |
| **3. All 22 requirements** | Guardrails, eval + before/after, prompt comparison, caching, rate limits, breaker, cost, observability, Locust + scaling, feedback, runbook. |
| **4. Hardening + extras** | Clean-clone test, report sections, two rehearsals of all 10 demo items, and the extras (§11). |
| **5. Freeze** | Review day, 30 Oct. Only bug fixes, no new features. `main` must boot from a clean clone. |

What this means in practice:
- **Merge often.** Open a PR into `main` whenever you have finished work. There is no daily limit, so don't sit on finished work.
- **Switch on as you go.** Tell Vismay the moment a seam's conformance test passes without its `xfail`, and he flips its `IMPL_*` in `.env.example`.
- **Phase 2 first.** The researcher (Namith) and the verifier and router (Vihaan) block demo items 2, 5, 6 and 10.

**Critical path (checked 2026-10-26).** Each person's file starts with *Next steps to 30 October*. What blocks the most:

| Waiting on | What is blocked until then |
|---|---|
| ~~Vihaan's PR into `main`~~ Done 26 Oct (PR #9); switched on for everyone in `.env.example` | (Was: gate, verifier, router, feedback, quarantine, eval runner; demos #4-#6; feedback form and reviewer console) |
| Namith: the researcher searches for every requirement it reports | Meaningful findings with a real LLM (demo #2); the prompt comparison (L2) and before/after (L3) numbers; cost per 100 runs |
| One eval run pair with the Groq key (researcher 1.0.0 vs 1.1.0), after both of the above | Namith's L2 comparison, Vihaan's L3 before/after, Vismay's cost per 100 runs (L5) |
| Nishkal's Locust runs | Demo #9 and the D6, A7 and D7 numbers; nobody else can produce them |
| The team's RDA decision (Nishkal + Vihaan) | Whether §4.1 (demo #10) can ever be `met`/`unmet`; until then the correct answer is `cannot_determine` |

---

## 10. Demo and report responsibilities

| # | Demo item (all 10 must be ready) | Lead |
|---|---|---|
| 1 | `docker compose up` from a clean clone → working system | Vismay |
| 2 | Valid request → routed recommendation, citations resolve to retrieved text | Namith |
| 3 | One run traced end to end (tool calls, queries, passages, prompt versions, per-step latency + cost) | Vismay |
| 4 | Malformed request rejected + quarantined, evidence no agent run started | Vihaan |
| 5 | Unanswerable case → escalation, not fabrication | Vihaan |
| 6 | Self-verification catches an unsupported answer → re-search or escalate | Vihaan |
| 7 | Prompt-injection attempt and guardrail response | Namith |
| 8 | Circuit breaker opens when provider is down; degradation path | Vismay |
| 9 | Locust vs declared SLO; failure concurrency; effect of `--scale` | Nishkal |
| 10 | The §4.1 "source of protein" case, handled correctly | Nishkal (with Namith + Vihaan) |

| Report section | Owner |
|---|---|
| Problem and scope; architecture diagram with deployment boundaries; async + reliability design; cost per 100 runs | Vismay |
| Agent design: topology, tools, loop limits, guardrails, prompt comparison | Namith |
| Verification design; data contract; evaluation results before/after; feedback | Vihaan |
| Chunking + embedding strategy; p95 target, measured results, bottleneck; caching effect | Nishkal |
| Design decisions + what was rejected; what did not work | everyone (from decision records and incidents) |

**Viva:** anyone can be asked about any part. Before the demo, each person walks the others
through their own part (one session, roughly an hour total).

**Marks (Evaluation 2, 40 → scaled to 8):**

| Criterion | Marks |
|---|---|
| Problem understanding / architecture | 10 |
| Presentation / teamwork | 10 |
| Engineering judgement | 10 |
| Report / code / docs | 10 |

---

## 11. Extras (for the CV)

These start only after that owner's required work for Phase 3 is done. Each person owns their own.

| Owner | Extras |
|---|---|
| Nishkal | Hybrid retrieval (BM25 + dense) + cross-encoder reranker; retrieval recall@k on eval supporting passages; claim-trigger map linking claim wording to Claims-regulation clauses; Alertmanager SLO burn-rate alerts |
| Namith | LangGraph checkpointing so a failed run resumes mid-graph; a prompt-injection red-team suite (30+ attacks) run in CI with pass rate; structured-output validation + auto-repair |
| Vihaan | RAGAS cross-check + LLM-judge calibration against hand labels (agreement score); eval as a CI regression gate; feedback → new eval scenarios loop; property-based tests for the gate |
| Vismay | Reviewer console (queue of `regulatory-review` runs, citations side by side with passages, accept/override → feedback); GitHub Actions CI (tests + Compose smoke + clean-clone check); live progress over SSE; PDF export of findings; webhook callback option |

---

## 12. Non-negotiables (every LLM session must respect these)

1. **The system never approves a label.** Output is a finding plus a route; a human decides.
2. **Every citation must resolve to text that was actually retrieved in this run.** Unverified answers go to `regulatory-review`.
3. **Escalate, don't invent.** Uncertain, conflicting, possibly exempt or out-of-scope cases all go to `regulatory-review` with a reason.
4. **No secrets, endpoints or model ids in the repo.** Everything comes from env.
5. **Embeddings are computed locally.** The LLM is a free tier behind our gateway, and its provider is swappable through config.
6. **Every free-text label field is untrusted input** (prompt injection).
7. **Everything runs in containers.** One `docker compose up` from a clean clone. `main` always boots.
8. **Labels are text only.** Never read images.
9. **Only edit your own paths.** Code against `packages/contracts/`; additive contract changes only.
10. **Only commit and push on your own branch.** Never on `main` or a teammate's branch, never force-push, and no AI attribution in commits or PRs.

---

## 13. Glossary (from `docs/course/00_GLOSSARY.pdf`), with what each means for us

- **Chunking:** splitting documents into passages before embedding. **For us:** keep the regulation, clause id and heading path in each chunk's metadata.
- **Groundedness:** the share of an answer's statements that the retrieved passages support.
- **Context relevance:** whether the retrieved passages were relevant to the question. An answer can be grounded on irrelevant passages.
- **Faithfulness:** whether the claims can be inferred from the passages. RAGAS calls it faithfulness; TruLens reports a near-equivalent as groundedness. **For us:** L3 needs both, so define them differently and say how each is computed.
- **Hallucination rate:** the share of *responses* with **at least one** unsupported or contradicted statement, computed from claim-level groundedness. **For us:** count it per response, not as an average.
- **Prompt injection:** text the model reads as instructions instead of data. **For us:** treat every free-text field as hostile, because it reaches an agent that holds tools.
- **Data contract:** the published spec of a valid request (fields, types, ranges, permitted values). It binds both the caller and the service.
- **Ingestion boundary:** the *single* point where data is accepted or refused. Everything downstream may assume valid data.
- **Quarantine:** rejected records stored *with* their errors instead of being discarded.
- **Data freshness:** when the index was built, from which document versions, and how many chunks it has.
- **Deployment boundary:** everything deployed, scaled and restarted as one unit. Two modules in one container share one boundary.
- **Idempotent:** safe to re-run. **For us:** the index must not duplicate or corrupt, so use stable chunk ids and upserts.
- **Correlation ID:** attached on arrival and carried through every service and agent step.
- **Structured logging:** machine-parseable records with named fields. *"A log that can be queried, not just read."*
- **SLO / SLI / SLA:** the target committed to *before* measuring / the measurement itself / the contractual version. We declare an SLO.
- **p50 / p95:** the median and the tail. Agent runs have long tails, and averages hide them.
- **RPS:** throughput. High RPS with a bad p95 isn't a healthy service.
- **Circuit breaker:** after N consecutive failures, stop calling the dependency for a cooldown period and fail fast.
- **Exponential backoff / bounded retry:** each retry waits longer, and the number of attempts is capped.
- **Stub service:** a stand-in returning fixed responses, so tests measure *our* system.
- **Graceful degradation:** a reduced but defined mode. *"A queued request, a cached response or an honest error is degradation; a stack trace is not."*
