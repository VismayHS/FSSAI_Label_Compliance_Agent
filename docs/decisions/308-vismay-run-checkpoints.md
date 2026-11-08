# 308: Run checkpoints: LangGraph's Postgres saver, keyed by run id, resumed by RQ's retry of an abandoned job (Vismay)

- **Status:** Accepted, 2026-11-08
- **Extra:** Namith's "LangGraph checkpointing so a run interrupted mid-graph can resume" (`docs/contexts/Namith.md`).
- **Code:** `packages/agents/fssai_agents/checkpoints.py`, `graph.py`; `apps/worker/fssai_worker/dispatch.py`,
  `jobs.py`, `__main__.py`.
- **Tests:** `packages/agents/tests/test_checkpoints.py`, `apps/worker/tests/test_worker.py`.

## Context

- **What happened before.** If a worker died mid-run (OOM, a redeploy, `docker kill`), nothing re-ran the job. The
  run stayed `running` for ever, and the client polled until it gave up. The A2 failure table said "restarts from the
  beginning", but nothing actually restarted it.
- **What blocked checkpointing.** The pipeline's graph state carried the live `RunContext` (budget, step trace,
  event log). A checkpointer can't serialise that object.
- **Why it matters on the free tier.** A real run costs about 10k tokens, and Groq allows about 16 runs a day. Re-running classification
  and a finished research attempt after a crash wastes quota that the review needs.

## Options considered

1. **Re-queue and restart from the beginning.** Simple, but it pays for every finished LLM call again.
2. **Redis saver (`langgraph-checkpoint-redis`).** It needs the RedisJSON and RediSearch modules, but our Redis is the plain
   image. Swapping it for Redis Stack changes a service three other features depend on.
3. **Postgres saver (`langgraph-checkpoint-postgres`)** on the database the run store already uses (chosen).

## Decision

- **State.**
  - The `RunContext` moved out of the graph state into LangGraph's runtime context (`context_schema`), which is
    never checkpointed.
  - The state is now only contract models plus the trace so far (`steps`, `prompt_versions`).
  - A checkpoint is written after every node. The thread id is the run id.
- **Resume.** When a run id starts with a checkpoint present:
  - the saved trace is restored into the new context;
  - the graph continues at the interrupted node, so finished nodes don't run again;
  - the step and tool-call budgets count what was already done;
  - the wall clock starts again, because it measures this attempt;
  - if the checkpoint belongs to a different request, it is discarded;
  - if the graph had already finished, its saved result is returned.
- **The researcher's inner graph is compiled with `checkpointer=False`.**
  - LangGraph otherwise gives a checkpointer to every graph invoked inside a node.
  - The researcher's own state holds the live context.
  - An interrupted research attempt is therefore redone from its start.
- **Deletion.** A run that returns a result, complete or not, deletes its checkpoint. A crash, or a process that
  dies, keeps it.
- **Safety.** Deserialisation is limited to an allowlist of the contract schema types. A tampered checkpoint row then can't rebuild
  arbitrary classes.
- **Who re-runs the job.**
  - The job is enqueued with `Retry(max=1)`. `execute_run` never raises, so RQ retries only an *abandoned* job,
    meaning one whose worker died.
  - If the retry's worker also dies, the `worker_lost` failure callback marks the run `failed` with a reason, so
    polling ends.
  - Workers look for abandoned jobs every `WORKER_MAINTENANCE_S` (60 s).
- **Configuration.**
  - `PIPELINE_CHECKPOINTS`: empty = off (`.env.example`), `memory`, or `postgres`. Compose's worker uses
    `postgres`.
  - If the database is unreachable, checkpoints turn off with a warning, and the worker still starts (`main` must
    boot).

## Consequences

- **Measured on the stack (8 Nov, real Groq).**
  - Run `de30e15a…` had its worker killed 2 s into research. It was re-queued automatically and resumed at
    `research` with 3 steps restored.
  - It completed with one classification step in the trace, and the step indices were continuous.
  - It took 456 s, because RQ checks for maintenance only between blocking queue reads, which wait
    `worker_ttl − 15` = 405 s by default.
  - The worker now sets `worker_ttl` to the interval + 15 s. The pass then runs every 60 s (checked in the log).
    The job's started-registry entry still has to expire first, at the job timeout + 60 s.
- **Under-counted cost.** LLM calls made inside the node that was interrupted are not in the resumed trace. They were
  paid for, but the checkpoint never saw them.
- **Leftover rows.** A run whose worker dies and is never retried leaves its checkpoint rows behind. They are small,
  and only the "worker died twice" path leaves them.
- **Not resumed.** A run that ends incomplete because the provider is down (`ProviderUnavailable`) is not resumed. It
  returns an honest incomplete result, as before (demo #8).
