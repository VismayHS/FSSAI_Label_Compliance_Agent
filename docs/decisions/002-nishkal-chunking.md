# 002: Clause-aware chunking, local embeddings, hybrid retrieval

- **Owner:** Nishkal · **Status:** Accepted, built (`libs/ingest`, `libs/retrieval`)
- **Requirements:** L1 (chunking and embedding strategy, partial re-embed), D2 (idempotent pipeline), F4, A1 tool backends

## Context

The corpus is two FSSAI compendia. A compendium prints the principal regulation and then, right after
each amended provision, the substituted text, between "Substitution of highlighted provision" and
"[Operationalized w.e.f. …]". The labelling requirements and the claim conditions sit in different
regulations that do not refer to each other (spec §3). The §4.1 condition is one row of a table
(Schedule I, item 11) that runs across a page break.

Three failure modes follow:

1. A fixed-size splitter cuts table rows. The protein row becomes "11. Protein Source 10% of RDA per
   100 g for solids …" on one chunk and "or 5% of RDA per 100 kcal" on the next.
2. Superseded text is indexed as if it were in force. For example, the original "Low sugar: not more
   than 5 g" sits next to the substituted "6 g", and both look equally authoritative.
3. A query about the label ("protein declared on the nutrition panel") does not resemble the claim
   condition, so one embedding search returns Labelling passages only.

## Decision

### Chunking: by clause, never across one (`fssai_ingest/chunker.py`)

- **Parse the structure** of the text layer: regulations "5. Nutrition claims.-" numbered in sequence;
  markers (1) (2A) (a) (i) (A) at line start, accepted only as the next marker at an open level or the
  first of a new level. So "(2), (3) and 1.9 of schedule II" stays text, and "(i)" after "(h)" is the
  letter i unless "(h)" ends in a lead-in (":" or "-"). Schedules hold tables: a header ("Sl. No …") starts
  row numbering. Each row, such as "11. Protein Source …", is one unit, whatever page breaks it crosses;
  page-repeated headers are dropped.
- **Amendments.** Units inside a substitution block replace the units with the same clause id and their
  sub-clauses. Those originals are marked `superseded`. An omission supersedes the unit before it. A
  words-only substitution becomes a separate in-force `partial` unit on the same clause. The block's
  "[Operationalized w.e.f. …]" note is kept as the chunk's `effective` date.
- **Group into chunks.** A clause whose whole subtree fits in `CHUNK_MAX_CHARS` (default 1200) is one
  chunk. Otherwise it is split into its sub-clauses, recursively. A single oversized unit is split at
  sentence boundaries into numbered parts. Superseded and amended text never merges with other text.
  Each merged sub-clause keeps its character span, so `get_clause("9(2)")` still returns just 9(2).
  Bare headings ("5. Nutrition claims.-") are not chunks; they live on in their sub-clauses'
  `heading_path`.
- **Metadata per chunk:** `regulation`, `clause_id` ("5(3)(c)", "Schedule I, item 11"), `heading_path`
  (regulation title, chapter, schedule title with its "[See regulation …]" cross-reference and column
  names, then the parents' first lines, then the amendment status), `doc_version`, `page`, `status`,
  `amendment`, `effective`. `passage_id` is `<regulation>:<clause_id>[~superseded|~substituted|~inserted|~partial][#pN]`,
  readable in traces and stable across runs.
- **Context header.** The embedded text is `regulation name › heading path › clause id` followed by the
  verbatim text. Citations quote only the verbatim text.

Result on the corpus: 425 chunks (373 in force, 52 superseded), all ≤ 1200 characters; all 19 rows of the
in-force Schedule I are whole. The 1200-character cap keeps a chunk at roughly the 256-token window of
the embedding model, which silently truncates longer input, so the end of a long clause would never be
embedded.

**How this addresses the cross-regulation problem (spec §3).** The decisive passage carries the words a
claim query uses ("Nutrient Content Claim", "Protein", "Source", "See regulation 5 (3)") in its own
embedded text, not three chunks away. The Schedule I header also records which regulation points at it
(5(3)), so a search for the rule ("claims must meet Schedule I") and a search for the condition find
each other. Exact clause ids let the agent follow a cross-reference with `clause_lookup` instead of
another fuzzy search. Excluding superseded text by default (`RETRIEVAL_INCLUDE_SUPERSEDED=0`) means the
agent cannot ground a finding in wording that no longer applies.

### Embeddings: local sentence-transformers, normalised, via LangChain + FAISS

- The model name comes only from `EMBEDDING_MODEL` (D4). The deployment uses the small MiniLM-class
  model the spec suggests (§12): 384-dimensional, CPU-only, ≈ 90 MB, so it fits next to the stack in
  6–8 GB of Docker memory and indexes the corpus in about 9 s (47 chunks/s on a laptop CPU). It is
  embedded locally, so it costs nothing and needs no API key.
- Vectors are L2-normalised; FAISS (LangChain's `FAISS` vector store, flat index) ranks by L2, which
  equals cosine ranking on unit vectors. At 425 chunks an exact flat index is faster than any
  approximate one and needs no tuning.
- `EMBEDDING_MODEL=hashing` is a deterministic, download-free lexical stand-in. It is used by the tests
  and offline smoke runs only, never for reported numbers.

### Retrieval: hybrid by default (`fssai_retrieval/faiss_retriever.py`)

Dense similarity, BM25 over the same embedded text, and claim-trigger hints are fused by reciprocal rank
(k = 60). The hints come from `corpus/claim_triggers.yaml`: claim word + nutrient → Schedule I row, plus
5(3), Schedule II and 2(1)(l). The regulation filter is applied before ranking, so it never starves k.
Measured on 28 hand-labelled queries (`corpus/eval/retrieval_queries.jsonl`, real model):

| Config | hit@1 | hit@3 | hit@5 | hit@10 | MRR | §4.1 phrasings in top 5 |
|---|---:|---:|---:|---:|---:|---:|
| dense only | 0.643 | 0.821 | 0.857 | 0.929 | 0.736 | 1 of 3 |
| BM25 only | 0.679 | 0.821 | 0.857 | 1.000 | 0.776 | 2 of 3 |
| hybrid | 0.643 | 0.964 | 0.964 | 0.964 | 0.800 | 3 of 3 |
| hybrid + claim hints (default) | 0.679 | 0.964 | 1.000 | 1.000 | 0.823 | 3 of 3 |

Dense search alone misses the claim condition for two of the three §4.1 phrasings: the spec §5 failure,
measured. Exact terms ("source", "protein", "RDA") rescue it. The hint map is a hint, fused like a third
ranker, never forced in. With hints off, hybrid still finds all three.

### Idempotent build and partial re-embedding (D2, L1)

`python -m fssai_ingest build --corpus corpus/raw --out $INDEX_DIR --reembed none|changed|all`.

- Chunk id = `passage_id`: stable across runs and independent of the text.
- `chunk_table.json` records each vector's text hash and model.
- New chunks are added and vanished ones deleted, in place (LangChain `add_embeddings` / `delete`).
- `--reembed changed` re-embeds only chunks whose text or model changed.
- `none` refuses (exit 3) rather than mix stale and fresh vectors.
- A model change rebuilds the store, because a new model may change the vector size.
- An unchanged corpus rewrites nothing, not even `built_at`.
- `index_manifest.json` records `built_at`, `index_version`, document versions and sha256, chunk counts,
  model, dimension and throughput. The worker exposes them as metrics (D2).

## Rejected

- **Fixed-size or recursive character splitting (LangChain `RecursiveCharacterTextSplitter`).** It cuts
  the Schedule I table across the page break and mixes superseded with in-force text.
  `test_real_protein_row_is_whole_and_in_force` guards against exactly that.
- **Indexing only the latest text and dropping superseded provisions.** This loses the audit trail. A
  reviewer asking "what did 5(3) say before 2021?" gets nothing. Superseded text stays in the index,
  marked, and is excluded from search by default.
- **One chunk per regulation.** These are too long for a 256-token embedding window; most of the text
  would never be embedded.
- **A larger embedding model.** More memory in every worker replica (A7) and a slower index build. The
  measured misses were vocabulary misses, which BM25 fixes cheaply.
- **Chroma.** It would work. FAISS needs no server, and the whole index is a few MB on a read-only volume.
- **Cross-encoder reranking by default.** It is supported (`RERANKER_MODEL`) but off: it adds a second
  model download and a forward pass per candidate on every search, and hybrid + hints already reaches
  hit@5 = 1.0 on our queries. It stays an extra to measure later, with a harder query set.

## Consequences

- The worker image needs `fssai-retrieval[embeddings]` (CPU torch) and the indexer's model cache volume,
  mounted read-only with `HF_HUB_OFFLINE=1`.
- If the model cannot load, the retriever logs it, increments `fssai_retrieval_degraded_total` and
  serves BM25 only rather than failing every run (alert `RetrievalDegraded`).
- `langchain-community` logs a deprecation notice (the package is being split up); the FAISS store is
  pinned below 1.0. If it is removed, `faiss` is used directly behind the same `index.py` boundary.
