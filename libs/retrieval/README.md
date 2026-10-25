# fssai_retrieval (`libs/retrieval`)

Search and exact clause lookup over the regulation index (F4, L1), with the Redis retrieval cache (D7).
Owner: Nishkal · tasks N2.2, N3.3 in [`contexts/Nishkal.md`](../../contexts/Nishkal.md) · design:
decisions [002](../../docs/decisions/002-nishkal-chunking.md) and [003](../../docs/decisions/003-nishkal-caching.md).

| File | What |
|---|---|
| `fssai_retrieval/faiss_retriever.py` | `FaissRetriever`, the `Retriever` seam: hybrid search (dense + BM25 + claim hints, RRF), exact `get_clause`, index reload |
| `fssai_retrieval/index.py` | the on-disk index format shared with `fssai_ingest`; clause-id normalisation; embeddings (`EMBEDDING_MODEL`) |
| `fssai_retrieval/bm25.py` | dependency-free BM25 |
| `fssai_retrieval/hints.py` | claim-trigger hints from `corpus/claim_triggers.yaml` |
| `fssai_retrieval/cache.py` | Redis cache for query vectors and results; in-process fallback |
| `fssai_retrieval/evaluate.py` | recall@k / MRR against labelled queries or `eval/scenarios.jsonl` |

```bash
<venv-python> -m pip install -e "libs/retrieval[test,embeddings]"   # embeddings = sentence-transformers (CPU torch)
<venv-python> -m pytest libs/retrieval -q                           # builds a small test index from corpus/raw
FSSAI_QUALITY_INDEX=data/index <venv-python> -m pytest libs/retrieval/tests/test_retrieval_quality.py   # real-model recall
<venv-python> -m fssai_retrieval.evaluate --index data/index        # the recall table in the report
```

**Switched on with** `IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever` and `INDEX_DIR` pointing
at an index built by `fssai_ingest`. It passes `conformance.check_retriever` in every mode.

| Env | Default | |
|---|---|---|
| `INDEX_DIR` | `/data/index` | built by the indexer |
| `RETRIEVAL_MODE` | `hybrid` | `dense`, `bm25` |
| `RETRIEVAL_CLAIM_HINTS` | `1` | fuse `claim_triggers.yaml` hints |
| `RETRIEVAL_INCLUDE_SUPERSEDED` | `0` | search superseded originals too |
| `CACHE_ENABLED`, `CACHE_TTL_S`, `REDIS_URL` | `1`, `86400` | cache (decision 003) |
| `RERANKER_MODEL` | empty | optional cross-encoder |

The query embedding model is the one recorded in `index_manifest.json`, not `EMBEDDING_MODEL`, so queries
and corpus are always embedded alike. If the model cannot load, search continues on BM25 and
`fssai_retrieval_degraded_total` counts it. Metrics: `fssai_retrieval_seconds`,
`fssai_retrieval_cache_total`, `fssai_retrieval_empty_total`, plus the index freshness gauges
(`fssai_index_*`, `fssai_ingest_chunks_per_second`).
