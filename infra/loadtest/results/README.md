# Load-test results (D6, A7, D7)

Owner: Nishkal. Target declared first in [`../SLO.md`](../SLO.md): **full_run p95 ≤ 60 s at 5 concurrent
runs, ≤ 1 % failed**, with the stub LLM (mean 1.5 s, p95 4 s).

> **Status (2026-10-27): not yet measured on the full stack.** The full Compose stack is on `main` now,
> so the matrix can be run as soon as the stub-LLM replies are in (`apps/stub_llm/fssai_stub_llm/fixtures/`).
> The tooling is built and has been
> smoke-tested end to end against the API in inline mode on the fake pipeline. Those smoke numbers are
> not SLO results and are deliberately not recorded here. Fill in the tables below from real runs;
> every number must come from a folder in this directory.

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
| 1 | 1 | | | | | | | | |
| 1 | 2 | | | | | | | | |
| 1 | 5 | | | | | | | | |
| 1 | 10 | | | | | | | | |
| 1 | 20 | | | | | | | | |
| 3 | 1 | | | | | | | | |
| 3 | 2 | | | | | | | | |
| 3 | 5 | | | | | | | | |
| 3 | 10 | | | | | | | | |
| 3 | 20 | | | | | | | | |

### Matrix: cache off (same settings)

*(paste `summarize.py` output)*

### What to write once measured

- **Met at 5 concurrent?** Yes or no, with the p95.
- **Failure concurrency:** the first step whose p95 > 60 s, per worker scale.
- **Bottleneck:** the component, with the evidence. Expected, and to be confirmed rather than assumed:
  each RQ `SimpleWorker` runs one job at a time (decision 302), so with one worker, runs queue behind
  each other. If p95 at C users ≈ C × single-run time, queue wait is the bottleneck, and `--scale
  worker=3` should push the failure point out about 3×, until shared CPU or the stub's concurrency
  becomes the limit.
- **Effect of `--scale worker=3`:** throughput and p95 at each step, against one worker.
- **Effect of caching:** p95 and cost per run, cache on vs. off. The retrieval-level effect is already
  measured in decision 003: a hit saves ~15 ms per search, so a run-level change smaller than the noise
  is the expected and honest result.
