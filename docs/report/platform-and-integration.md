# Platform and integration

Owner: Vismay. Report sections: problem and scope; architecture with deployment boundaries; asynchronous
execution and reliability; cost per 100 runs. Sources: decisions 301–304, `docs/architecture.md`, and the
measurements cited inline.

## Problem and scope
A regulatory affairs analyst checks a packaged-food label before print against two FSSAI regulations that
never refer to each other: Labelling & Display 2020 says what must appear, and Advertising & Claims 2018
sets the conditions a claim must meet. The service returns one finding per requirement, each with
citations to regulation and clause, and a route (`clear-for-print`, `revise-and-recheck`,
`regulatory-review`). It never approves a label. Labels arrive as text; model training, cloud deployment
and images are out of scope.

## Architecture and deployment boundaries
One `docker compose up -d --build` from a clean clone starts eleven services
([decision 304](../decisions/304-vismay-deployment-boundaries.md), diagram in [architecture.md](../architecture.md)):

- **Request path.** `web` (nginx, static build, proxies the API) sends to `api` (FastAPI: gate, 202, polling,
  trace), which enqueues into `redis` (RQ). `worker` × N runs the pipeline and writes to `postgres`
  (runs and steps).
- **Supporting jobs.** `indexer` (one-shot index build), and `stub-llm` (load tests and the breaker demo).
- **Observation.** `prometheus`, `grafana`, `jaeger`, `cadvisor`.

Each boundary has its own scaling, failure and release profile:
- The API scales on HTTP requests and carries no agent code (about 300 MB).
- Workers scale on runs in flight and carry the model and index (about 2.3 GB).
- The index build runs only when the corpus changes.
- The stub keeps load tests from measuring a provider we don't control.

We rejected a single app container, because every replica would carry the model and `--scale` couldn't
isolate run throughput. We also rejected one container per agent: that adds network hops inside one run,
for no measured benefit.

**Rejected or failed requests never start work (D1).** The order on submit is: client id, size limit,
gate (rate limit, validation, quarantine), save as `queued`, enqueue. A reject returns `422` with field
errors and a quarantine id, and no run or job exists. `tools/scripts/smoke.py` checks this on every run.

## Asynchronous execution
`POST /v1/runs` answers `202` with a run id, status URL and trace URL. The client polls with backoff
([decision 301](../decisions/301-vismay-async-polling.md)). Polling won over callbacks for three reasons:
- **Every client can poll.** The browser, Locust, curl and the eval runner can all do it, but a webhook
  needs the caller to run a reachable server.
- **It is stateless on the server.** There are no outbound calls to arbitrary URLs, which would be an
  SSRF risk.
- **It measures D6 directly.** Polling gives the "submission to final result" time the SLI needs.

A webhook stays an extra. Runs go through RQ on Redis
([decision 302](../decisions/302-vismay-queue-rq.md)) to `SimpleWorker` processes:
- **Interchangeable workers.** The payload is plain JSON, everything a run produces goes to Postgres, and
  breaker state lives in Redis, so any worker can take any job.
- **Measured scaling (2026-10-25).** With `--scale worker=3`, three replicas took jobs from one queue, and
  Prometheus discovered all three through DNS with no config change.

**Traceability (D5).** Every response carries a correlation id that is attached to the run, the job, every
step and every JSON log line. The API's submit span travels inside the job payload, so Jaeger shows one
trace from the HTTP request to the worker's run. `GET /v1/runs/{id}/trace` reconstructs a run from the
database alone: the request, every step with its inputs and outputs (queries, full passages, LLM
messages), prompt versions, latency, tokens and cost per step and per agent, queue wait, verdict and route.

## Reliability (A5)
All LLM calls go through `fssai_llm_gateway`:
- **Timeouts.** Every attempt has a timeout, capped by the run's remaining wall-clock budget.
- **Bounded retry.** Only timeouts, connection errors, 429, 5xx and malformed replies are retried, with
  exponential backoff and full jitter. `Retry-After` is honoured, and a retry never goes past the run
  deadline.
- **Circuit breaker.** One breaker per provider, kept in Redis so every worker shares it. It opens after N
  consecutive failures, then fails fast. After a cooldown, one trial call is allowed through: if it
  succeeds the breaker closes, and if it fails the breaker opens again.
- **Degradation.** If a fallback model is configured, the run continues on it and is marked `degraded`.
  Otherwise the gateway raises `ProviderUnavailable`, and the pipeline returns `complete=false` routed to
  `regulatory-review` with the reason. That is an honest error, not a stack trace.

**Demonstrated (2026-10-25, demo #8):** `python -m fssai_llm_gateway.demo` ran in the worker container
against the stub, with breaker state in Redis:
- one healthy call;
- the stub switched off, then three failing calls, each retried once; the breaker opened;
- the next calls failed in 0–1 ms without any HTTP request;
- the stub restored and the 8 s cooldown over, the trial call succeeded and the breaker closed.

**Other failures.**
- A failed enqueue saves the run as `failed` and answers `503`.
- A crash inside the pipeline saves the run as `failed` with its error type.
- `/readyz` refuses readiness in queue mode with an in-memory run store.
- A failed index build no longer stops the stack from booting (incident `2026-10-25-vismay-indexer-py311-worker-crashloop`).

## Cost per 100 runs (L5)
Cost is computed at call time from the provider's token counts and `LLM_PRICE_*_PER_1K`, recorded on each
`llm` step, and stored per step in `run_steps`. `tools/scripts/cost_report.py` and the Grafana `Cost (L5)`
dashboard show cost per 100 runs, cost by step and agent, and the largest single driver, all from the same
table.

All figures are priced at the provider's published list price for the primary model, $0.15 per million prompt tokens
and $0.60 per million completion tokens (Groq's model documentation). On the free tier we actually pay $0.

Measured twice on the Compose stack with all 11 parts real, runs one at a time about a minute apart (Groq's free tier
allows 8,000 tokens a minute):

| | 26 Oct: researcher before decision 102 | **27 Oct: researcher with the sweep (decision 102)** |
|---|---|---|
| Runs | 8 (the three load-test payloads) | 8 eval scenarios: §4.1, fibre, sugar, fat, allergen, all declarations, small pack, out of scope |
| Mean cost per run | $0.002759 (p95 $0.003539) | $0.002645 (p95 $0.004334) |
| **Cost per 100 runs** | $0.28 | **$0.26** |
| Largest single cost driver | `act` (researcher): 64% | **`draft` (researcher): 56%** (7 calls, 35,601 tokens) |
| Researcher share of spend | 91% | 92% |

27 Oct by step (`python tools/scripts/cost_report.py --since 2026-10-27T18:04:50`):

| LLM step | Calls | Prompt tokens | Completion tokens | Cost | Share |
|---|---|---|---|---|---|
| `draft` (researcher) | 7 | 21,185 | 14,416 | $0.0118 | 56% |
| `act` (researcher) | 8 | 33,063 | 4,307 | $0.0075 | 36% |
| `classify` (classifier) | 8 | 3,498 | 2,101 | $0.0018 | 8% |

What this does and does not show:
- **The sweep moved the cost, not the total.** Searching every requirement deterministically replaced most `act`
  rounds (23 calls on 26 Oct, 8 now), and the draft now reads passages for every requirement, so its prompt and its
  reply (one finding per requirement) are the largest items.
- **The mean hides the mix.** A run that researches and drafts costs $0.0034–0.0046 (mean $0.0037, so about $0.37 per
  100 such runs). An out-of-scope run stops after the classifier ($0.0002). The two runs that hit the 90 s limit
  stopped before their draft ($0.0010–0.0013). A workload of only in-scope labels sits near $0.37 per 100.
- **Cheaper options, in order of effect:** fewer passage characters in the draft (`RESEARCHER_DRAFT_CHARS`, which
  also helps the 90 s limit), passage ids instead of full text in `act`, and the smaller fallback model for the
  classifier. The whole eval set (30 scenarios) is measured by the prompt-comparison run pair (Namith, Vihaan).
- **Not a quality result.** All 8 runs ended in `regulatory-review` (safe: none was wrongly cleared). Five escalated
  because grounding dropped quotes that were not verbatim (14 of the 42 drafted quotes were shortened with "..."), and
  two hit the 90 s wall-clock limit while waiting for Groq's per-minute token budget. The verifier marked nothing
  unsupported. Both causes are on the team's critical path (`docs/contexts/LLM_Context.md` §9).
- On the fakes and the stub every recorded cost is $0, and the report says so instead of inventing a number.

## What did not work, and what we changed
- **The indexer crashed in its container.** The tests ran on Python 3.13 locally, while the containers
  run 3.11. CI now tests on 3.11.
- **One missing setting could stop the whole stack.** A hard Compose dependency on the optional index job
  meant a missing `EMBEDDING_MODEL` stopped the stack from serving at all. The dependency is now optional.
  Both are in the incident log.
