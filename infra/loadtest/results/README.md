# Load-test results (D6, A7, D7)

Owner: Nishkal. Target declared first in [`../SLO.md`](../SLO.md): **full_run p95 ≤ 60 s at 5 concurrent
runs, ≤ 1 % failed**, with the stub LLM (mean 1.5 s, p95 4 s).

> **Status (2026-11-06): measured on the full stack.** Two matrices, run 5–6 Nov 2026 at commit `e224c5a`:
> [`20261105T195833Z-cache-on/`](20261105T195833Z-cache-on/) and
> [`20261105T210335Z-cache-off/`](20261105T210335Z-cache-off/). Every number below comes from those folders
> (`python infra/loadtest/summarize.py <folder>`).
>
> **Setup.** Full Compose stack in queue mode (RQ on Redis, Postgres run store), every real implementation
> switched on (LangGraph pipeline, hybrid FAISS + BM25 retriever, gate, guardrails, verifier, router, LLM
> gateway), the gateway pointed at `stub-llm` (`STUB_LATENCY_MEAN_S=1.5`, `STUB_LATENCY_P95_S=4`, no
> injected failures), `RATE_LIMIT_PER_MIN=100000`. 5 minutes per step after a 30 s warm-up. Host: Windows 11,
> 12 logical CPUs, Docker Desktop with 7.6 GB. `meta.json` shows `settings: null` because these values were
> set in `.env`, which the containers read, not in the shell that ran Locust.
>
> Every run completed and routed `regulatory-review`. The stub's canned replies lead there, so these
> numbers measure latency and throughput only, never routing quality (that is the eval set, L3).

## How to produce the results

1. `.env` for a load test, in addition to the usual values:
   ```
   LLM_BASE_URL=http://stub-llm:8080/v1
   LLM_MODEL=stub
   STUB_LATENCY_MEAN_S=1.5
   STUB_LATENCY_P95_S=4
   RATE_LIMIT_PER_MIN=100000   # load generator users are not abusive clients; leave rate limiting out of p95
   IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever
   ```
2. Install Locust on the host: `<venv-python> -m pip install -r infra/loadtest/requirements.txt`
3. Run the matrix, once with the cache on and once with it off (restart the workers between them):
   ```
   python infra/loadtest/run_matrix.py --host http://localhost:8000 --compose --scales 1 3 --label cache-on
   # set CACHE_ENABLED=0 in .env (containers read .env, not your shell), then:
   docker compose up -d --force-recreate worker
   python infra/loadtest/run_matrix.py --host http://localhost:8000 --compose --scales 1 3 --label cache-off
   ```
   Each folder gets Locust CSVs per step (`w<workers>_u<users>_stats.csv`), the route and outcome
   counts, and `meta.json` with OS, CPU, Docker memory, git commit and stub settings.
4. `python infra/loadtest/summarize.py infra/loadtest/results/<folder>` prints the table. Paste it below and commit
   the folder.
5. While a step runs, take the bottleneck evidence:
   - the Grafana *Service overview* run p95 vs. HTTP p95. A large gap is queue wait.
   - worker CPU per replica (cAdvisor).
   - one slow run's trace (`GET /v1/runs/{id}/trace`, Jaeger): where its time went, queue vs. LLM vs.
     retrieval.

## Results

### Matrix: cache on

| workers | users | runs | runs/s | p50 (s) | p95 (s) | max (s) | failed | submit p95 (s) | SLO |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 63 | 0.21 | 4.2 | 8.4 | 11.5 | 0.0% | 0.130 | met |
| 1 | 2 | 65 | 0.21 | 8.4 | 14.0 | 28.3 | 0.0% | 0.092 | met |
| 1 | 5 | 76 | 0.24 | 20.0 | 30.0 | 35.6 | 0.0% | 0.180 | met |
| 1 | 10 | 73 | 0.21 | 45.0 | 57.0 | 61.1 | 0.0% | 0.082 | met |
| 1 | 20 | 76 | 0.20 | 97.0 | 117.0 | 120.6 | 0.0% | 0.180 | **missed** |
| 3 | 1 | 61 | 0.20 | 4.2 | 9.8 | 12.0 | 0.0% | 0.066 | met |
| 3 | 2 | 115 | 0.38 | 4.7 | 8.9 | 18.1 | 0.0% | 0.089 | met |
| 3 | 5 | 192 | 0.63 | 7.4 | 13.0 | 17.4 | 0.0% | 0.150 | met |
| 3 | 10 | 201 | 0.65 | 15.0 | 21.0 | 25.6 | 0.0% | 0.095 | met |
| 3 | 20 | 205 | 0.62 | 31.0 | 40.0 | 44.4 | 0.0% | 0.170 | met |

### Matrix: cache off (same settings, `CACHE_ENABLED=0`, workers recreated)

| workers | users | runs | runs/s | p50 (s) | p95 (s) | max (s) | failed | submit p95 (s) | SLO |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 65 | 0.22 | 4.2 | 9.3 | 14.4 | 0.0% | 0.069 | met |
| 1 | 2 | 52 | 0.17 | 11.0 | 19.0 | 23.4 | 0.0% | 0.110 | met |
| 1 | 5 | 65 | 0.19 | 24.0 | 36.0 | 43.1 | 0.0% | 0.089 | met |
| 1 | 10 | 72 | 0.21 | 46.0 | 51.0 | 56.2 | 0.0% | 0.097 | met |
| 1 | 20 | 82 | 0.22 | 87.0 | 100.0 | 106.8 | 0.0% | 0.190 | **missed** |
| 3 | 1 | 65 | 0.22 | 4.2 | 8.3 | 13.5 | 0.0% | 0.069 | met |
| 3 | 2 | 114 | 0.37 | 4.7 | 10.0 | 13.4 | 0.0% | 0.066 | met |
| 3 | 5 | 195 | 0.63 | 7.3 | 12.0 | 19.2 | 0.0% | 0.072 | met |
| 3 | 10 | 204 | 0.64 | 15.0 | 19.0 | 23.2 | 0.0% | 0.073 | met |
| 3 | 20 | 211 | 0.63 | 31.0 | 36.0 | 41.7 | 0.0% | 0.150 | met |

### Findings

- **Met at 5 concurrent? Yes.** One worker, cache on: p95 **30 s** against the 60 s target, 0 % failed
  (cache off: 36 s). No step in either matrix failed a single run.
- **Failure concurrency.** One worker: the SLO first fails at **20 users** (p95 117 s cache on, 100 s
  off); 10 users is the last step that meets it (57 s, close to the line). Three workers: met at every
  step up to 20 users (p95 40 s), so the failure point is **beyond 20**. We did not run a 30- or 40-user
  step; from the queueing model below we would expect it near 30 users, but that is a projection, not
  a measurement.
- **Bottleneck: queue wait behind a single serial worker** (each RQ `SimpleWorker` runs one job at a
  time, decision 302). The evidence:
  - With one worker, throughput is flat at **≈ 0.21 runs/s** from 1 to 20 users. Adding users adds no
    work done, only waiting.
  - p50 grows linearly with users, at about one single-run time (≈ 4.5 s) per user ahead in the queue:
    4.2 s at 1 user, 20 s at 5, 45 s at 10, 97 s at 20.
  - One slow run's trace from the 1-worker, 20-user step (run `81173cbf4df24e8da8c30bc0d5f64117`,
    `GET /v1/runs/{id}/trace`): `queue_wait_ms` **89 305** against **3 907 ms** of execution
    (classifier 1.8 s, researcher 2.0 s; 3 LLM calls, 6 tool calls). **96 % of that run's time was
    spent waiting in the queue.** The execution time is almost all stub-LLM latency; retrieval,
    Postgres and the API are not where the time goes.
  - Submission stays fast throughout (submit p95 ≤ 0.19 s), so the API and the gate are not the limit.
- **Effect of `--scale worker=3`:** throughput rises from 0.21 to **0.63–0.65 runs/s, ≈ 3×**, and
  plateaus from 5 users onwards, which is three workers saturated. At 20 users, p50 falls from 97 s to
  31 s (≈ ⅓) and p95 from 117 s to 40 s. Workers are stateless, so scaling needed no code change.
  At 1 user, three workers change nothing (one run at a time either way). The next limits after the
  worker count are the stub's per-call latency and, for a real provider, the free tier's tokens per
  minute (see `docs/contexts/LLM_Context.md` §4), not our CPU.
- **Effect of caching: within noise.** Cache off vs. on, p95 moves in both directions (1 worker: 36 vs.
  30 s at 5 users, but 51 vs. 57 s at 10 and 100 vs. 117 s at 20; 3 workers: 12 vs. 13, 19 vs. 21 and
  36 vs. 40 s), and throughput is the same. This is the result decision 003 predicted: a cache hit
  saves ~15 ms per search (under 0.2 s per run), against several seconds of model calls and, under
  load, tens of seconds of queue wait. The cache saves no LLM cost, because LLM responses are
  deliberately not cached. It is kept for the worker CPU it saves, not as a p95 lever.
