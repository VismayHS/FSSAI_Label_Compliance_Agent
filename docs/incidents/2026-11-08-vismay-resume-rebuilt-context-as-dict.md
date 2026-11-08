# 2026-11-08: a resumed run crashed because the researcher's inner graph had been checkpointed too

- **Author:** Vismay
- **Severity:** the first resume on the real stack failed the run instead of finishing it; found before merging
- **Component:** `packages/agents/fssai_agents/researcher.py` (with run checkpoints, decision 308)

## What happened

- **First kill test.** A run (`ea835900…`) had its worker killed during research, but the job was never re-queued.
  The API image predated the change that adds `Retry(max=1)` to the job. This is the same lesson as
  `2026-11-06-vismay-stale-worker-image`: rebuild every image a change touches. The dispatcher lives in the worker
  package, but the API is what enqueues.
- **The resume.** After re-queueing that job by hand, the pipeline resumed correctly at `research`, with its 3 steps
  restored. Then it crashed:
  `AttributeError: 'dict' object has no attribute 'check_budget'` in the researcher's `act` node.

## How it was noticed

- The run ended `failed` with `internal error (AttributeError)`.
- Its checkpoint rows were still in Postgres: a crash keeps them by design.

## Cause

- **Inherited checkpointer.** LangGraph gives the parent's checkpointer to any graph invoked inside a node. The
  researcher runs its own LangGraph graph, and that state holds the live `RunContext`. The killed run had
  checkpointed the researcher's state, context included, under the `research` task's namespace.
- **The crash.** On resume, LangGraph reloaded that inner state. The context came back as a plain dict.
- **Why the tests missed it.** The unit tests used `FakeResearcher`, which is not a LangGraph graph.

## Fix

- The researcher's graph is compiled with `checkpointer=False`, so it never inherits one. An interrupted research
  attempt is redone from its start.
- `test_a_run_interrupted_inside_the_real_researcher_resumes` uses the real researcher and a scripted LLM. It
  reproduces the crash without the fix.
- The second kill test (`de30e15a…`) resumed and completed automatically.

## Lesson

- A test double that is simpler than the real thing can hide the exact property under test. Here, that was "is
  this a LangGraph graph".
- For anything stateful across a process boundary, run the real path once on the stack before calling it done.
