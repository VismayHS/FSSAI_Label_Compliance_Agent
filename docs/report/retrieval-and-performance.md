# Retrieval and performance

Report section · Owner: Nishkal · Requirements: L1, D2, D5 (metrics, tracing backend, dashboards), D6,
A7 (measurement), D7 (caching), F4 (retrieval side). The design decisions behind it are records 001–004
in `docs/decisions/`.

## 1. Corpus

Two FSSAI compendia, each the principal regulation with every amendment printed next to the text it
replaces:

- Advertising and Claims Regulations 2018, Version-II (16.11.2021), 23 pages.
- Labelling and Display Regulations 2020, Version-VI (22.02.2023), 42 pages.

Both have a full text layer, so no OCR was needed. Provenance is in `corpus/manifest.json`: source URL,
the URL the bytes came from, version and sha256. The product category is breakfast cereals (decision
001). Health supplements are out of scope, because Schedule I Note 1 of the Claims regulation sends their
claims to a regulation outside the corpus.

## 2. Chunking and embedding strategy (L1)

**The difficulty (spec §3).** The condition that decides the §4.1 case is a table row in the Claims
regulation: Schedule I, item 11, "Protein · Source · 10% of RDA per 100 g for solids …". The Labelling
regulation, which a label question naturally retrieves, never points to it. On top of that, the
compendium prints superseded and substituted versions of the same provisions one after the other.

**Chunking: by clause, never across one.** A structural parser reads the text layer:

- regulations, numbered in sequence;
- sub-regulations and clauses, as markers accepted only in sequence;
- schedule tables, one unit per row whatever page breaks the row crosses;
- amendment blocks, whose units replace the originals. The originals stay in the index, marked superseded.

A clause that fits in 1200 characters is one chunk; a bigger one is split into its sub-clauses. Each
chunk carries regulation, clause id, heading path (including the schedule's "[See regulation 5 (3) …]"
cross-reference and column names), document version, page and amendment status. A context header, `regulation › heading path ›
clause`, is embedded with the verbatim text; citations quote only the verbatim text. On this corpus:
**425 chunks, 373 in force, all 19 in-force Schedule I rows whole.**

**Embedding.** A small local sentence-transformers model (MiniLM-class, 384 dimensions; the name is in
`EMBEDDING_MODEL` only), L2-normalised, in a LangChain FAISS flat index. Building the index embeds 47
chunks/s on a laptop CPU, about 9 s for the corpus.

**Retrieval** fuses three rankings by reciprocal rank:

- dense similarity;
- BM25 over the same text;
- claim-trigger hints, which map claim wording such as "source" + "protein" to the Schedule I row, 5(3)
  and Schedule II. This is a hint, not a filter.

Superseded text is excluded from search by default. Exact clause lookup (`get_clause`) normalises how a
clause id is written and returns a merged clause or a sub-clause slice, so the agent can follow
cross-references precisely.

**Re-embedding without a rebuild (L1, D2).** Chunk ids are stable passage ids. A table records each
vector's text hash and model, and `--reembed changed` replaces exactly the changed vectors in place. A
rerun on an unchanged corpus rewrites nothing. Freshness (built at, versions, sha256, chunk counts,
throughput) is published as Prometheus metrics by the worker that loads the index.

## 3. Retrieval quality

28 hand-labelled queries (`corpus/eval/retrieval_queries.jsonl`), every relevant clause checked against
the PDFs. Run with `python -m fssai_retrieval.evaluate`; real model:

| Config | hit@1 | hit@3 | hit@5 | hit@10 | recall@5 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| dense only | 0.643 | 0.821 | 0.857 | 0.929 | 0.857 | 0.736 |
| BM25 only | 0.679 | 0.821 | 0.857 | 1.000 | 0.857 | 0.776 |
| hybrid | 0.643 | 0.964 | 0.964 | 0.964 | 0.964 | 0.800 |
| **hybrid + claim hints** (default) | 0.679 | 0.964 | **1.000** | 1.000 | **1.000** | **0.823** |

The §4.1 question, in three phrasings: dense search alone puts the claim condition in the top 5 for
**one** of them. Hybrid finds it for all three, with or without hints. This is the spec §5 argument
measured on our own corpus: a request about a label does not resemble the provision that decides it.
Exact terms ("source", "protein", "RDA") carry the match that the embedding misses. Hybrid with hints
missed nothing in the top 5. Dense-only misses in the top 5 were two of the three "source of protein"
phrasings, "high protein claim requirement", and the Schedule II synonyms query ("can 'provides protein'
be used …").

## 4. SLO, measured results and bottleneck (D6, A7)

**Target** (declared before measuring, `loadtest/SLO.md`): complete-run p95 ≤ 60 s at 5 concurrent runs
(one worker, stub LLM with mean 1.5 s and p95 4 s per call), and ≤ 1 % failed runs.

- **Why 60 s:** an analyst's pre-print check against tens of minutes by hand. Long enough for the
  verify-and-retry loop; inside the 90 s run bound.
- **Why 5:** a realistic busy moment for a team of 10–20 analysts.

**Method.** Locust users submit, poll every 0.5 s and report `full_run` from submission to terminal
state. Steps of 1, 2, 5, 10 and 20 users, 5 minutes each, at 1 and 3 workers, cache on and off.

**Results.** *Pending the full-stack run (see `loadtest/results/README.md`).* The tooling has been
verified end to end against the API on the fake pipeline. Those numbers measure the fakes, not the
system, and are not reported.

**Expected bottleneck, to confirm or refute with the results.** Each RQ worker runs one job at a time,
so with one worker, concurrent runs queue. If p95 at C users is close to C times the single-run time, the
queue is the bottleneck, and three workers should move the failure point out about three times. The
dashboard separates queue wait (client `full_run` minus worker run time) from worker CPU and stub
latency, so the cause can be named rather than assumed.

## 5. Caching (D7)

Query embeddings and retrieval results are cached in Redis, keyed by model and by index version. A
rebuild therefore invalidates the cache without a flush, and an unreachable Redis degrades to an
in-process cache instead of failing the run. Whole-run and LLM-response caches were rejected: they would
return verdicts made with older prompts or indexes, and would skip the verification the spec grades
(decision 003).

**Measured at the retrieval level** (real model, 28 queries × 5): a search takes 15.7 ms p50 and
18.8 ms p95 uncached, and 0.18 ms and 0.22 ms on a cache hit. That saves about 15 ms per search, or
under 0.2 s per run, against several seconds of model calls. So retrieval caching cuts worker CPU but is
not a p95 lever, and it saves no LLM cost. The run-level effect on p95 and cost per run comes from the
cache-on/cache-off load matrix (pending, section 4). The expected result is a change within noise.

## 6. Observability (D5)

- `fssai_observability` gives every service JSON-lines logs (with `run_id` and `correlation_id`, and the
  RunContext events flattened to fields), OTel tracing to Jaeger over OTLP/HTTP (a no-op when not
  configured), and trace-context helpers to carry a trace across the queue.
- The stack (`deploy/compose/observability.yml`) runs Prometheus, scraping every service including each
  worker replica via DNS discovery, plus Grafana, Jaeger, cAdvisor and Redis/Postgres exporters.
- The *Service overview* dashboard shows run and HTTP p50/p95, error rate, throughput, availability,
  CPU, memory and uptime per container, retrieval latency and cache hit ratio, and index freshness.
- Burn-rate alerts on the SLO are defined in `observability/prometheus/rules/slo.yml`.

## 7. What did not work, or not first time

- **Dense retrieval alone** missed the §4.1 condition for two of three phrasings (section 3).
- **The first chunker** turned "3 g of fat per 100 g" into Schedule I row 3, shifting every later row,
  and read the sentence end "…Schedule – IIA.]" as a new schedule. It was caught by reading the parse
  against the PDF, not by any metric. Recall would have looked fine while every citation pointed at the
  wrong row (incident `2026-10-25-nishkal-chunker-table-rows`).
- **fssai.gov.in reset every connection** from our network, so the corpus came from archived copies of
  the official URLs, with provenance recorded (incident `2026-10-25-nishkal-fssai-site-unreachable`).
- **The model download failed TLS verification** behind antivirus HTTPS interception, while curl worked.
  Fixed locally without weakening verification in code (incident `2026-10-25-nishkal-model-download-tls`).
- **Open: the protein RDA is not in the corpus.** The Schedule I condition is in % of RDA, and both
  regulations defer the RDA to ICMR. Comparing a declared value needs an external, cited reference value
  or an escalation (`docs/eval1/section-4.1-passages.md`).
