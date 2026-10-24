# 302 · Queue: RQ on Redis, in-process workers, inline mode for local development

**Status:** accepted · **Owner:** Vismay · **Requirements:** A4, A5, A7, D3

## Context
A4 needs a queue or task runner between submission and execution. A7 needs
`docker compose up --scale worker=3` to work. Redis is already in the stack for the retrieval cache,
rate-limit counters and the shared circuit-breaker state. The agent interfaces in `contracts/` are
synchronous (`Pipeline.run(request, ctx) -> RunResult`).

## Options
| Option | For | Against |
|---|---|---|
| **RQ** (Redis Queue) | Small, synchronous jobs match our sync pipeline; job ids we choose (= run id); actively maintained; easy to test with fakeredis | Linux-only worker in practice (fork/SIGALRM); no built-in scheduling we'd use |
| arq | asyncio, Redis-based | Async-only jobs would wrap our sync pipeline in threads; low maintenance activity |
| Celery | Feature-rich, many brokers | Heavy configuration and concepts for one queue and one job type |
| Redis list + `BLPOP` by hand | No dependency | Re-implements job ids, timeouts, failure records and visibility ourselves |
| Postgres `SKIP LOCKED` | One less moving part | Polling DB load; Redis is already present |

## Decision
RQ on Redis, queue `fssai-runs`, job id = run id, job timeout = `RUN_MAX_WALL_S + 30 s`.

- Workers run RQ's **`SimpleWorker`** (`python -m fssai_worker`): each job runs inside the worker process
  instead of a fork per job. The pipeline is built once per process, Prometheus counters accumulate on
  the worker's own `/metrics` port (a forked child's counters would vanish with it), and there is no
  per-run state left behind. Scaling is by container count (`--scale worker=N`).
- The job payload is plain JSON (`run_id`, `correlation_id`, the validated request). Everything a run
  produces goes to the `RunStore`, so any worker can take any job (A7).
- `RUN_DISPATCH=inline` runs jobs in a small thread pool inside the API process. It exists so that a fresh
  clone works with nothing but `uvicorn` while Compose is not up; `/readyz` reports it, and refuses to be
  ready in queue mode with an in-memory run store (workers could never update it).

## Consequences
- Queue mode needs a shared `RunStore` (Postgres, `libs/run_store`) before Compose can serve runs.
- A failed enqueue (Redis down) saves the run as `failed` and returns `503`: an honest error, not a lost run.
- Local Windows development uses inline mode; the queue worker runs in its Linux container (it also
  starts on Windows thanks to a timer-based job timeout, for debugging).
