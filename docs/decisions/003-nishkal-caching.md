# 003: Caching: query embeddings and retrieval results in Redis; no whole-run cache

- **Owner:** Nishkal · **Status:** Accepted, built (`packages/retrieval/fssai_retrieval/cache.py`)
- **Requirement:** D7 (caching, justified and measured; rate limiting is Vihaan's half)

## Context

A run makes several retrieval calls (the researcher's searches and lookups, plus the verifier's clause
lookups). Agents repeat queries: a retry after a failed verification searches again, and many labels
trigger the same claim conditions. The spec also asks what a cache does to p95 and cost per run.

## Options

| Cache | Saves | Risk |
|---|---|---|
| Query embeddings | Model inference per search: ~15 ms CPU | None: an embedding depends only on (model, text) |
| Retrieval results | Embedding + FAISS + BM25 + fusion per search | Stale after a rebuild, unless the index version is part of the key |
| LLM responses | Provider tokens: the cost driver | Different prompt versions, temperatures or contexts give different answers; hides provider behaviour from the load test |
| Whole runs (request hash → result) | Everything | Returns a verdict made with an older prompt, index or model. Bypasses verification, the step the spec grades. Makes load tests with repeated payloads meaningless. |

## Decision

- **Cache query embeddings and retrieval results**, in Redis, shared by every worker replica. Keys:
  - `fssai:emb:<sha(model, query)>`: the float32 vector.
  - `fssai:retr:<sha(index_version, mode, hints, include_superseded, reranker, regulation, k, normalised query)>`:
    a list of `(passage_id, score)`. Passages are rebuilt from the loaded index on a hit, so a hit can
    never return text the index no longer has.
- **Invalidation is by key, not by flush.** `index_version` changes whenever a vector or chunk changes.
  The worker reloads the index when `index_manifest.json` changes, so new keys are used from then on.
  TTL `CACHE_TTL_S` (default 24 h) bounds memory.
- **Never fail a run because of the cache.** If Redis is unreachable or errors, the cache logs once and
  falls back to an in-process LRU (`fssai_retrieval_cache_total{backend="memory"}` shows it).
- `CACHE_ENABLED=0` switches it off for the with/without comparison.
- **No whole-run cache and no LLM-response cache.** Correctness beats latency here. A label resubmitted
  after a prompt or index change must be checked again. The LLM gateway (Vismay) is the right place if
  an LLM cache is ever added, keyed on prompt version.

## Measured effect (retrieval level, real model, 28 queries × 5)

| | p50 | p95 |
|---|---:|---:|
| cache off | 15.7 ms | 18.8 ms |
| cache on, first pass (miss) | 16.2 ms | 19.6 ms |
| cache on, repeat (hit) | 0.18 ms | 0.22 ms |

A hit saves ~15 ms per search. With ~5–10 searches per run that is under 0.2 s per run, against
several seconds of model calls. **Retrieval caching is not what moves p95 or cost.** It cuts worker CPU
per run (the embedding forward pass), which matters once several replicas share a CPU. It changes LLM
cost per run by zero, because no tokens are saved. The run-level effect on p95 under load (cache on vs
off, same matrix) is measured with the stack in `infra/loadtest/results/` and reported in
`docs/report/retrieval-and-performance.md`.

## Consequences

- Redis is now on the retrieval path. It is optional by design: the fallback means a Redis outage only
  costs the cache.
- The cost question belongs to the LLM side: the largest single cost driver is the model calls (L5, Vismay).
