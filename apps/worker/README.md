# worker

Executes runs (A4, A7). Owner: Vismay. `python -m fssai_worker` consumes the `fssai-runs` queue on Redis. In
Compose it runs as the `worker` service and scales with `docker compose up -d --scale worker=3`.

| File | What |
|---|---|
| `fssai_worker/jobs.py` | `execute_run`: load the run, mark it running, call `build("pipeline").run(...)`, save the result or an honest failure |
| `fssai_worker/dispatch.py` | How a submitted run reaches `execute_run`: `RUN_DISPATCH=queue` (RQ) or `inline` (a thread pool, for local development) |
| `fssai_worker/__main__.py` | The queue consumer, its metrics server (`WORKER_METRICS_PORT`) and tracing |

The worker keeps nothing on its own disk: runs live in Postgres, breaker state in Redis, and the index on a
read-only volume. That is what makes `--scale` safe.
