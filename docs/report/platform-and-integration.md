# Platform and integration

Owner: Vismay. Report sections: problem and scope; architecture with deployment boundaries; asynchronous
execution and reliability; cost per 100 runs. Sources: decisions 301–304, `docs/architecture.md`, and the
measurements cited inline. Numbers marked *pending* are filled in from real-provider runs before submission.

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

First measurement, 26 Oct 2026: 8 real runs on the Compose stack (the three load-test payloads, run one at a time),
priced at the provider's published list price for the primary model, $0.15 per million prompt tokens and $0.60 per
million completion tokens (Groq's model documentation). On the free tier we actually pay $0.

| | Value |
|---|---|
| Runs measured | 8 (`python tools/scripts/cost_report.py --since 2026-10-26T16:00`) |
| Mean cost per run | $0.002759 (p95 $0.003539) |
| **Cost per 100 runs** | **$0.28** at list price |
| Largest single cost driver (step) | the researcher's `act` step: 64% of spend (23 calls, 49,367 tokens); the researcher as a whole is 91% |

| LLM step | Calls | Prompt tokens | Completion tokens | Cost | Share |
|---|---|---|---|---|---|
| `act` (researcher) | 23 | 34,266 | 15,101 | $0.0142 | 64% |
| `draft` (researcher) | 5 | 7,717 | 7,868 | $0.0059 | 27% |
| `classify` (classifier) | 8 | 3,586 | 2,431 | $0.0020 | 9% |

What this does and does not show:
- The sample is small, and in all 8 runs the researcher stopped after a few searches (Namith is fixing that), so a
  run that searches every requirement will cost more. The number is re-measured on the eval set once that lands.
- The driver is clear either way: the researcher's reasoning loop (`act`), whose prompt grows with every passage it
  has read. Cheaper options, in order of effect: fewer `act` rounds (`RESEARCHER_MAX_ITERATIONS`), passing passage
  ids instead of full text back into the loop, and the smaller fallback model for the classifier.
- On the fakes and the stub every recorded cost is $0, and the report says so instead of inventing a number.

## What did not work, and what we changed
- **The indexer crashed in its container.** The tests ran on Python 3.13 locally, while the containers
  run 3.11. CI now tests on 3.11.
- **One missing setting could stop the whole stack.** A hard Compose dependency on the optional index job
  meant a missing `EMBEDDING_MODEL` stopped the stack from serving at all. The dependency is now optional.
  Both are in the incident log.
