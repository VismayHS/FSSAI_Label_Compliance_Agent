# Vismay: Platform & Integration (+ Frontend)

> Your plan, checklist and LLM prompts. **Only you edit this file** (and `LLM_Context.md`). Tick
> boxes as you go, and add notes at the bottom.

## Your mission
You make it **a production service, not a notebook**:
- the API and async run model, the queue and the workers,
- the LLM gateway with timeouts, retries, circuit breaker and cost accounting,
- Docker Compose, config hygiene, correlation ids and run reconstruction,
- the web client.

You're also the **integrator and repo owner**. You keep `main` booting (otherwise it's zero
marks), flip the `IMPL_*` switches as teammates finish, and assemble the report.

**Requirements you own:** F1 (endpoint), F8, A4, A5, A8 (frontend, your extra), L5, D3, D4, D5 (correlation id + run reconstruction)
**Units:** 1 (architecture, interfaces), 2 (containerisation, reliability), 3 (cost monitoring), 4 (orchestration, containerisation)
**Demo leads:** #1 clean-clone `docker compose up`, #3 one run traced end to end, #8 circuit breaker + degradation
**Report sections:** problem and scope; architecture with deployment boundaries; async + reliability design; cost per 100 runs. You also **assemble** the full report.

**Your paths:**
- `services/api/` (except Vihaan's two routers), `services/worker/`, `services/web/`, `libs/llm_gateway/`, `libs/run_store/`
- `docker-compose.yml`, `deploy/compose/{api,worker,redis,postgres,web}.yml`, `deploy/postgres/init/*-vismay-*.sql`
- `Makefile`, `README.md`, `.github/`, `.env.example` (structure + shared section)
- `contexts/LLM_Context.md`, `observability/grafana/dashboards/cost.json`
- `docs/architecture.md`, `docs/eval1/project-plan.md`, `docs/decisions/*-vismay-*`, `docs/incidents/*-vismay-*`
- `docs/report/platform.md`, plus assembling `docs/report/`

## What you depend on, and what you provide

Nothing below blocks you.

| You consume | From | Until it's real, use |
|---|---|---|
| `RequestGate` | Vihaan | `FakeRequestGate` (shape validation + in-memory quarantine) |
| `Pipeline` | Namith | `ReferencePipeline` on fakes (the default registry), which already gives a complete walking skeleton |
| Stub LLM (breaker demo, load tests) | Nishkal | `FakeLLM` with `FAKE_LLM_FAIL=1`, or point `LLM_BASE_URL` at a dead port |
| `fssai_observability` (JSON logs, OTel) | Nishkal | stdlib `logging` + `ctx.event()`. Call his `setup_*` functions once they exist (they're no-ops when unconfigured). |
| Feedback / quarantine routers | Vihaan | Nothing is needed; the API auto-mounts `app/routers/*.py` |

| You provide | To | Through |
|---|---|---|
| The running stack (API, worker, Redis, Postgres) | everyone | `docker compose up`, `make smoke` |
| `LLMClient` (gateway) | Namith, Vihaan | `IMPL_LLM=fssai_llm_gateway.client:GatewayLLMClient` |
| `RunStore` (Postgres) | Vihaan (live scoring) | `IMPL_RUN_STORE` |
| `/v1/runs/{id}/trace` | Nishkal (bottleneck analysis), demo #3 | HTTP |

---

## Prompt 0: start every LLM session with this
```
I'm Vismay, one of 4 people building the "FSSAI Label Compliance Agent" (a university ML System
Design & AgentOps project). I own the platform and integration and the repo. Before anything
else, read from the repo:
1. contexts/LLM_Context.md  (project, team, architecture, rules; stable)
2. contexts/Vismay.md       (my workstream, tasks, status)
3. contracts/fssai_contracts/*.py  (schemas, interfaces, context, fakes, pipeline, registry)

Rules for this session:
- I may only create/edit: services/api/ (except routers/feedback.py and routers/quarantine.py),
  services/worker/, services/web/, libs/llm_gateway/, libs/run_store/, docker-compose.yml,
  deploy/compose/{api,worker,redis,postgres,web}.yml, deploy/postgres/init/*-vismay-*.sql, Makefile,
  README.md, .github/, .env.example, observability/grafana/dashboards/cost.json, and my docs files.
- contracts/ changes only as separate additive "contracts:" PRs; propose them to me first.
- Everything goes through the registry (fssai_contracts.registry.build), never imports of teammates'
  classes. Fakes are the default.
- No credentials, endpoints or model ids anywhere in the repo: env only, documented in .env.example.
- Every service: /healthz, /readyz, /metrics, JSON logs with correlation_id. Python 3.11.
- Every behaviour gets a test; Compose changes must keep `make smoke` green.
- Git: I work only on my own branch `vismay` (check `git branch --show-current`). Never commit or
  push to main or a teammate's branch, never force-push, never --no-verify, merge origin/main
  (never rebase). No Co-Authored-By/"Generated with" lines. Commit or push only when I ask.
Summarise my current task in 3 lines, then wait for my go.
```

---

## Phase 0: setup (days 1–2)

- [ ] **S0.1 Set up the GitHub repo.**
  - Add Nishkal, Namith and Vihaan as collaborators, and write their GitHub usernames into the table in `LLM_Context.md` §1.
  - The four personal branches (`nishkal`, `namith`, `vihaan`, `vismay`) already exist on GitHub, along with `CONTRIBUTING.md`, `.githooks/` and `scripts/setup_dev.py`. Run `python scripts/setup_dev.py vismay` yourself, and from now on work only on `vismay` like everyone else.
  - Apply the GitHub settings in CONTRIBUTING.md §8: merge commits only (no squash or rebase), don't auto-delete head branches, a ruleset on `main` (require a PR, block force-pushes and deletion), and a ruleset on the four personal branches (block force-pushes and deletion).
  - Add `.github/CODEOWNERS` from the ownership table in LLM_Context §5, so the right person is auto-requested.
  - Fill in the dates in LLM_Context §9.
  - Check with the instructor that a team of 4 is OK (the spec says 2–3).
  - Decide whether the repo stays public. It contains the course PDFs; you can make it private under Settings → General.
- [ ] **S0.2 Create package skeletons.** Create `services/api`, `services/worker` and `libs/llm_gateway` packages (each with its own `pyproject.toml`), plus a `Makefile` with `install`, `test`, `up`, `down` and `smoke` targets.

## Phase 1: Evaluation 1 (week 1): the walking skeleton

- [ ] **S1.1 Build the API and worker on fakes (A4, F1).** This is the system's first end-to-end path.
  - `POST /v1/runs`:
    1. read `X-Client-Id` (required) and `X-Correlation-Id` (optional, otherwise generate one),
    2. call `build("gate").check(raw, client_id)`,
    3. on reject → 422 with the errors and `quarantine_id`, and **no enqueue**,
    4. on rate limit → 429,
    5. on accept → create a `RunStatus(queued)` in the `RunStore`, enqueue `{run_id, correlation_id, request}`, and return `202 {run_id, status_url}`.
  - `GET /v1/runs/{id}` and `GET /v1/runs/{id}/trace`.
  - The worker pops a job, builds a `RunContext(run_id, correlation_id)`, runs `build("pipeline").run(...)` and saves the result.
  - Routers in `app/routers/*.py` are auto-mounted.
  - Add `/healthz`, `/readyz` (checks Redis and Postgres) and `/metrics`.
  - **Queue choice:** RQ or arq on Redis, justified in a decision record; see S3.3.
  ```
  (after Prompt 0) Build services/api (FastAPI) and services/worker per Vismay.md V1.1. Use
  fssai_contracts.registry.build for gate, pipeline and run_store. Implement the Postgres RunStore in
  libs/run_store (package fssai_run_store, installed by both api and worker) with tables from
  deploy/postgres/init/10-vismay-runs.sql: runs (status, timestamps, client_id, correlation_id, result
  jsonb) and run_steps (one row per StepRecord) so a run can be reconstructed by SQL too. Auto-include every `router` in app/routers/*.py. Correlation
  id middleware adds it to logs and response headers and passes it into the job. Tests with TestClient,
  fakeredis and an in-memory run store: 202 path, 422 path enqueues nothing, 429 path, status polling.
  ```
- [ ] **S1.2 Set up Compose (D3, D4).**
  - The root `docker-compose.yml` only `include:`s the files in `deploy/compose/`. Your fragments are api, worker, redis, postgres and web.
  - Every service gets a health check and `depends_on: condition: service_healthy`.
  - The worker has no fixed `container_name` or host port, so `--scale worker=3` works.
  - All config comes through `env_file: .env`. Keep `.env.example` complete.
  - Add `make smoke`: it brings up the stack, POSTs the §4.1-style fake request, polls to completion and checks the route.
  ```
  (after Prompt 0) Write Dockerfiles (python:3.11-slim, non-root user, pip install ./contracts and
  the needed libs/* packages) and compose fragments per Vismay.md V1.2, plus the root docker-compose.yml
  using `include:`. Healthchecks for api (curl /healthz), redis (redis-cli ping), postgres (pg_isready);
  worker exposes metrics on a port without host mapping. Add Makefile targets up/down/logs/smoke where
  smoke = scripts/smoke.py (Python standard library only, so it runs on Windows and macOS) that submits
  the §4.1-style fake request, polls, and asserts the route. Verify it works from a clean clone with only `cp .env.example .env`.
  ```
- [ ] **S1.3 Assemble the Evaluation 1 project plan** in `docs/eval1/project-plan.md`. Build it from LLM_Context §§2–4, 9 and 10, Nishkal's passages, Vihaan's test values and Namith's topology draft. Add a first `docs/architecture.md` diagram **with deployment boundaries marked**.

## Phase 2: real end-to-end (by end of week 2)

- [x] **S2.1 Build the LLM gateway (A5, L5).** `fssai_llm_gateway.client:GatewayLLMClient` implements `LLMClient`:
  - **Provider adapter:** OpenAI-compatible, configured by `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`, with an optional fallback `LLM_FALLBACK_*`.
  - **Timeout on every call,** capped by `ctx.remaining_s()`.
  - **Bounded retry:** exponential backoff with jitter, only on retryable errors (429, 5xx, timeouts).
  - **Circuit breaker:** after N consecutive failures it opens, fails fast for a cooldown, then lets one trial call through (half-open). Keep the state in Redis so all scaled workers share it.
  - **Degradation path:** fallback model alias if one is configured, otherwise raise `ProviderUnavailable`. The pipeline then returns `complete=False` → `regulatory-review` with an honest reason.
  - **Cost at call time:** `cost = prompt_tokens × LLM_PRICE_PROMPT_PER_1K/1000 + completion × ...`, recorded on the `llm` step.
  - **Metrics:** calls, retries, breaker state and failures, by agent and step.
  ```
  (after Prompt 0) Implement libs/llm_gateway per Vismay.md V2.1 using httpx with explicit timeouts.
  Breaker: Redis keys (state, failure count, opened_at) with configurable threshold/cooldown; expose
  breaker_state gauge. Retry with exponential backoff + full jitter, max attempts from env, only on
  retryable errors. Record exactly one "llm" step per logical call (attempt count in output, retries
  counted in a metric), with prompt name/version, tokens and cost. Tests with respx/fakeredis: retries
  then success; retries exhausted → ProviderUnavailable; breaker opens after N failures and fails fast
  without HTTP calls; half-open recovery; cost calculation; fallback model used when configured.
  ```
- [x] **S2.2 Make every run reconstructible (D5).** `GET /v1/runs/{id}/trace` returns every step in order:
  - agent, kind and name,
  - input and output (queries, **full passages**, tool args),
  - prompt name and version,
  - latency, tokens and cost,
  - the verification verdict and the final route,
  - the correlation id and a Jaeger trace link.

  Call Nishkal's `setup_logging` and `setup_tracing` in the API and worker so the spans join up across the queue: carry the trace context inside the job payload.
- [x] **S2.3 Build web client v1 (A8, your extra).** `services/web` is a simple single page that:
  - shows a form, or a JSON paste box with a "load §4.1 example" button,
  - submits the request and polls,
  - shows the **route + reason**, each finding with its status, citations (regulation, clause, quote) and the **escalation path** (why it went to human review),
  - links to the trace.

  Appearance earns no marks, but keep it clean.
  ```
  (after Prompt 0) Build services/web as a minimal static app (plain HTML + vanilla JS or a tiny
  framework, served by nginx or by the API's StaticFiles) per Vismay.md V2.3. Read the API base URL
  from a runtime config.js generated from env at container start. Render citations with the quote
  highlighted, route as a coloured badge, escalation reason prominent, "not an approval" notice always
  visible. Include satisfactory/unsatisfactory feedback buttons that POST to /v1/runs/{id}/feedback.
  ```
- [ ] **S2.4 Integrate the real implementations.** As teammates merge, switch the `IMPL_*` variables in your local `.env` (and in `.env.example` comments) and run `make smoke` plus the §4.1 request on the real stack.

## Phase 3: all requirements (weeks 3–4)

- [ ] **S3.1 Make the circuit breaker demonstrable (A5).** Add a `make demo-breaker` target that points the gateway at the stub with `STUB_DOWN=1` (or a dead URL), submits runs, shows the breaker opening (metric and log), shows runs completing as `regulatory-review` with `complete=false` and an honest reason, then recovers.
- [ ] **S3.2 Report cost (L5).**
  - Build the `cost.json` dashboard: cost per run, cost per step name, tokens by agent.
  - Write a script that computes **cost per 100 runs** and the **largest single cost driver** (the step with the highest total cost) from the `run_steps` table, after a batch of real-provider runs. You can use Vihaan's eval set run 4–5 times.
- [ ] **S3.3 Write decision records.**
  - Async model: polling vs callback, and why. A4 requires a justification.
  - Queue choice.
  - Deployment boundaries (D3): why api, worker, indexer, redis, postgres and stub-llm are separate, considering scaling, failure isolation, independent release and resource profile.
- [ ] **S3.4 Audit for secrets (D4).** Add a CI check (or `make audit`) that greps for keys, URLs and model ids and fails on any hit.
- [ ] **S3.5 Keep the worker stateless (A7 support).** Nothing per-worker on disk, breaker state in Redis, and the index on a read-only volume. Support Nishkal's scaling runs.
- [ ] **S3.6 Finish the web client.** Feedback buttons work, and the escalation path is clear.

## Phase 4: hardening, extras, report

- [ ] **S4.1 Test from a clean clone (demo #1).** Write `scripts/clean_clone_test.py`: clone into a temp dir, `cp .env.example .env` (plus the provider key), `docker compose up -d`, wait for healthy, `make smoke`. Run it before every demo rehearsal.
- [ ] **S4.2 Write the README** so a stranger can run the system without help (the course will test this). Include:
  - prerequisites, then setup in three commands,
  - how to submit a request (curl and the web client),
  - where the dashboards are,
  - how to run eval and Locust,
  - links to the runbook, incident log, `.env.example` and eval set.
- [ ] **S4.3 Assemble the report.** Merge `docs/report/*.md` into the final report covering every point in spec §11, and run two rehearsals of all 10 demo items with the team.
- [ ] **S4.4 Write at least one incident entry** in `docs/incidents/`.
- [ ] **Extras:**
  - [ ] **GitHub Actions CI:** contract tests, each package's tests, `docker compose build`, and smoke on PRs
  - [ ] **Reviewer console:** a page listing `regulatory-review` runs, showing citations next to the retrieved passages, with accept/override actions → feedback
  - [ ] **Live progress over SSE** instead of polling
  - [ ] **PDF export** of a finding
  - [ ] **Webhook callback** option for A4

## CV line you'll be able to write
*"Built the production platform for a multi-agent LLM compliance service: FastAPI with async job
execution over a Redis queue and horizontally scalable workers, an LLM gateway with timeouts,
retries with backoff, a shared circuit breaker and per-step cost accounting, end-to-end
OpenTelemetry tracing with full run reconstruction, a 10-service Docker Compose deployment, and
the web client."*

## Pitfalls
- A 422 that still enqueues a job fails demo #4. Gate first, enqueue only on accept.
- Breaker state kept in process memory doesn't work with `--scale worker=3`.
- Free-tier limits: keep `RUN_MAX_*` tight, use the stub for anything repetitive, and check the spending limit.
- `include:` in Compose needs Compose v2.20+. Note the version in the README prerequisites.
- **Windows + macOS** (you develop on Windows, teammates on macOS, and the examiner may run the README on either; see LLM_Context §8.8):
  - `make` isn't installed by default. Keep every `make` target a thin wrapper over a plain `docker compose ...` command, and print those commands in the README too.
  - Write helper scripts in Python, or run them inside a container, rather than relying on bash.
  - `.gitattributes` forces LF line endings. Don't override it, or shell scripts and entrypoints break inside the Linux containers.
  - Run Docker Desktop with the WSL 2 backend.
- Your ownership of `main`'s health matters more than any single feature. Being the repo owner doesn't exempt you from the branch rules: your work also goes `vismay` → PR → `main`.

## Notes / log
**2026-10-24 (branch `vismay`)**
- Repo: one branch per person (CONTRIBUTING.md, `.githooks/`, `scripts/setup_dev.py`); shared AI skills in `skills/` (`python scripts/sync_skills.py install`).
- S0.2 partly: packages `services/api` (`app`), `services/worker` (`fssai_worker`), `libs/llm_gateway` exist with tests. Makefile waits for Compose.
- S1.1 done except the Postgres `RunStore` (`libs/run_store`): API on fakes, gate before enqueue, 400/413/422/429/503, correlation ids, JSON logs, `/healthz` `/readyz` `/metrics`, RQ queue + `python -m fssai_worker`, inline mode for local dev. `RunStatus` now carries `request` + `correlation_id` (additive contract change).
- S2.1 done: gateway with deadline-capped timeouts, full-jitter retry + Retry-After, per-provider breaker (Redis or memory), fallback marked degraded, cost per call. 15 tests.
- S2.2 done: `/v1/runs/{id}/trace` with request, every step, per-agent rollups, queue wait. Jaeger link waits for Nishkal's tracing.
- S2.3 done (v1): web client in `services/web` (decision 303, `PRODUCT.md`, impeccable direction "Pack Mark System"). Feedback buttons wait for Vihaan's endpoint (S3.6).
  - Impeccable finish review: two fix rounds, every scored item resolved; a last trace-layout regression (cost clipped below ~1400px) fixed after it, checked at 1280px. `services/web/DESIGN.md` + `.impeccable/design.json` record the shipped system. Review captures: `node services/web/scripts/capture.mjs services/web/.impeccable/review name=url[|selector]`.
- S3.3: decisions 301 (polling) and 302 (RQ) written; deployment boundaries record still to do with Compose.
- Next: Compose + Dockerfiles + Postgres run store + `scripts/smoke.py` (S1.2), then the breaker demo (S3.1) and `docs/architecture.md` (S1.3).
- Run locally: `uvicorn app.main:create_app --factory --env-file .env --port 8000`, then `npm --prefix services/web run dev` and open http://localhost:5173.
