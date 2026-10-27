# 2026-10-25: the indexer crashed in its container, and the real retriever crash-looped the worker

- **Author:** Vismay · **Severity:** the full stack could not serve real retrieval; caught during the first
  Compose bring-up, before `main` depended on it
- **Components:** `indexer` (`packages/ingest`, Nishkal), `worker` (`apps/worker`), `infra/compose/worker.yml`

## What happened

The first `docker compose up` from `.env.example` booted, and the smoke test passed on the fakes. Switching
on the real retriever (`IMPL_RETRIEVER=...FaissRetriever` and `EMBEDDING_MODEL` in `.env`) then failed in two
places at once:

```
indexer  | File ".../fssai_ingest/chunker.py", line 255
indexer  |     self.headings[key] += f" [{re.sub(r'^[\[(]\s*|\s*[\])]\s*$', '', line)}]"
indexer  | SyntaxError: f-string expression part cannot include a backslash
worker   | fssai_retrieval.index.IndexNotBuilt: no index in /data/index: run python -m fssai_ingest build ...
worker   | Restarting (1) 8 seconds ago
```

## How it was noticed

`docker compose ps -a` showed `indexer  Exited (1)` and `worker  Restarting`. The first run, from a clean
`.env.example`, had already shown a related warning: with `EMBEDDING_MODEL` empty, the indexer exits 1 by design.

## Cause

Two separate causes stacked:

1. **Python versions differed.** A backslash inside an f-string expression is legal only from Python 3.12.
   The development `.venv` runs Python 3.13, so all 32 ingest tests passed. The containers use the
   project's Python 3.11, where the module doesn't even import.
2. **The real retriever refuses to start without an index**, which is the right call, since silently
   serving nothing would be worse. The worker builds its pipeline at start-up, so it crash-looped instead
   of taking jobs.

A third risk was found on the way. The worker was meant to wait for `indexer: service_completed_successfully`.
A clean clone has an empty `EMBEDDING_MODEL`, so the indexer always fails there, and the worker would never
start: `docker compose up` would serve nothing at the demo.

## Fix

- `chunker.py`: the regex runs on the line above, outside the f-string. Output is unchanged, and the
  indexer container now builds and re-runs idempotently in about 3 s. This was a one-line fix in Nishkal's
  path, noted in his context file.
- `infra/compose/worker.yml`: the indexer dependency is `required: false`. A failed index build now
  degrades retrieval and no longer stops the stack from booting. Compose prints a warning instead.
- CI (`.github/workflows/ci.yml`) compiles every file and runs every package's tests on **Python 3.11**,
  the containers' version, so a 3.12-only construct fails the PR instead of the demo.

## Lesson

- Test on the Python the containers run, not the one on the laptop. A green local suite proved nothing
  about 3.11.
- A hard `depends_on` on an optional, environment-dependent job turns one missing setting into a stack
  that doesn't boot. Make dependencies hard only where the service truly cannot work without them.
- Run the clean-clone path (`tools/scripts/clean_clone_test.py`) after every change to Compose or `.env.example`.
