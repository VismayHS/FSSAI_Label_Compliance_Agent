# Nishkal: Knowledge & Performance

> Your plan, checklist and LLM prompts. **Only you edit this file.** Tick boxes as you go, and add
> notes at the bottom. Read `contexts/LLM_Context.md` first.

## Your mission
You own **what the system knows** and **how fast it runs**:
- the regulation corpus, the index and retrieval,
- caching, the metrics and tracing stack,
- the SLO and the load test.

If the research agent can't *find* the claim condition in the Claims regulation, the §4.1 case
fails. That makes you the lead on demo item 10 as well as item 9.

**Requirements you own:** L1, D2, D6, A7 (measurement), D7 (caching), D5 (metrics, tracing backend, dashboards), F4 (retrieval side)
**Units:** 1 (data contracts, freshness), 2 (observability, reliability), 3 (retrieval)
**Demo leads:** #9 Locust + scaling, #10 the §4.1 case
**Report sections:** chunking + embedding strategy; p95 target, results, bottleneck; caching effect

**Your paths** (edit nothing else):
- `corpus/`, `libs/ingest/`, `libs/retrieval/`, `libs/observability/`
- `services/stub_llm/`, `loadtest/`
- `observability/prometheus/`, `observability/grafana/provisioning/`, `observability/grafana/dashboards/service-overview.json`
- `deploy/compose/{indexer,stub-llm,observability}.yml`
- your section of `.env.example`
- `docs/eval1/section-4.1-passages.md`, `docs/decisions/*-nishkal-*`, `docs/incidents/*-nishkal-*`
- `docs/report/retrieval-and-performance.md`

## What you depend on, and what you provide

Nothing below blocks you.

| You consume | From | Until it's real, use |
|---|---|---|
| Compose skeleton, Redis, Postgres | Vismay | Run your code locally with plain Python; your Compose fragments only need `include:` in the root file |
| A pipeline to load-test | Namith / Vismay | The fake pipeline (`FakeLLM` with `FAKE_LLM_DELAY_S`) through Vismay's API. Before that exists, run Locust against your stub alone. |
| Prompt names to answer in the stub | Namith | The `[prompt:<name>@<version>]` tag convention (LLM_Context §6). Fall back to a generic JSON reply. |

| You provide | To | Through |
|---|---|---|
| `Retriever` (search, clause lookup) | Namith (researcher), Vihaan (verifier) | `IMPL_RETRIEVER` |
| Real clause ids + text for §4.1 | Vihaan (eval), Namith (prompts) | `docs/eval1/section-4.1-passages.md` |
| Logging, tracing and metric helpers | everyone | `fssai_observability` (no-op if env unset) |
| Stub LLM | Vismay (breaker demo), you (Locust) | `LLM_BASE_URL=http://stub-llm:8080/v1` |

---

## Prompt 0: start every LLM session with this
```
I'm Nishkal, one of 4 people building the "FSSAI Label Compliance Agent" (a university ML System
Design & AgentOps project). Before anything else, read from the repo:
1. contexts/LLM_Context.md  (project, team, architecture, rules; stable)
2. contexts/Nishkal.md      (my workstream, tasks, status)
3. contracts/fssai_contracts/*.py  (schemas, interfaces, context, fakes, pipeline, registry)

Rules for this session:
- I may only create/edit files under: corpus/, libs/ingest/, libs/retrieval/, libs/observability/,
  services/stub_llm/, loadtest/, observability/prometheus/, observability/grafana/provisioning/,
  observability/grafana/dashboards/service-overview.json, deploy/compose/{indexer,stub-llm,observability}.yml,
  my section of .env.example, and my docs files listed in Nishkal.md.
- Never edit contracts/ or other people's paths. If a contract must change, stop and propose the
  exact additive change and why.
- Code against the interfaces in contracts; use the fakes for anything owned by others.
- No credentials, endpoints or model ids in code: read env vars and add them to my .env.example section.
- Every behaviour gets a pytest test. Record tool steps with ctx.record() and events with ctx.event().
- Python 3.11, each package has its own pyproject.toml.
Summarise my current task in 3 lines, then wait for my go.
```

---

## Phase 0: setup (days 1–2)

- [ ] **N0.1 Set up and create package skeletons.** Clone the repo, create a venv, run `pip install -e "contracts[test]"` and `pytest contracts -q` (9 tests should pass). Create installable packages:
  - `libs/ingest` → `fssai_ingest`
  - `libs/retrieval` → `fssai_retrieval`
  - `libs/observability` → `fssai_observability`

  Each needs a `pyproject.toml`, an `__init__.py` and one trivial test. Open your first PR.
  ```
  (after Prompt 0) Create three installable Python packages: libs/ingest (fssai_ingest),
  libs/retrieval (fssai_retrieval) and libs/observability (fssai_observability). Each gets its own
  pyproject.toml (setuptools, python>=3.11, depends on fssai-contracts), an __init__.py with a one-line
  docstring, and tests/test_smoke.py that imports it. Keep the dependency lists minimal; I'll add
  real ones per task. Show me the commands to install all three in editable mode and run their tests.
  ```
- [ ] **N0.2 Get the corpus and propose a product category.**
  - Download both regulations from the official FSSAI site (fssai.gov.in): the Labelling & Display Regulations 2020 and the Advertising & Claims Regulations 2018, including the latest consolidated or amended versions if published.
  - Check each has a text layer (`pdftotext file.pdf - | head`).
  - Commit them to `corpus/raw/` together with `corpus/manifest.json`. For each file record: title, notification or version date, source URL, sha256, page count, and text-layer yes/no.
  - Post **two product-category options** with reasons in the group chat. Pick a category where protein claims are common. The team decides, and you write up the decision as `docs/decisions/001-nishkal-product-category.md`.
  ```
  (after Prompt 0) Write corpus/tools/manifest.py: a small script that scans corpus/raw/*.pdf and
  writes corpus/manifest.json with, per file: filename, title (from PDF metadata or first page),
  sha256, page_count, has_text_layer (true if extractable text on >=90% of pages), source_url and
  version_date (both read from a corpus/sources.yaml I maintain by hand). It must be idempotent and
  print a table. Add a test using a tiny generated PDF fixture.
  ```

## Phase 1: Evaluation 1 (week 1)

- [ ] **N1.1 Find the §4.1 passages (the reference answer).** Read the two regulations yourself; the LLM only helps you search. Find:
  - (a) the clause(s) in the **Claims 2018** regulation that set the condition for a "source of protein" claim (the exact threshold and basis, e.g. per 100 g, per 100 kcal or per serving, whichever the regulation actually says),
  - (b) the **Labelling 2020** clauses on declaring nutritional information (protein included),
  - (c) anything that modifies these (exemptions, definitions).

  Write `docs/eval1/section-4.1-passages.md` with the regulation, clause id, page and verbatim quote for each passage. Vihaan uses it to write the test values.
  ```
  (after Prompt 0) Help me locate passages, but quote only text that appears in the PDFs. Write a
  script corpus/tools/grep_pdf.py that extracts text per page (pypdf or pdfminer.six) and searches
  for terms with page numbers and ±3 lines of context. I'll run it for: "source of protein",
  "protein", "nutrition claim", "Schedule", "nutritional information", "exempt". Then help me
  structure docs/eval1/section-4.1-passages.md: per passage → regulation (FSS-AC-2018 / FSS-LD-2020),
  clause id, page, verbatim quote, why it matters for the §4.1 case. Never invent clause numbers or
  thresholds; if unsure, mark "TO VERIFY".
  ```
- [ ] **N1.2 Declare the SLO before measuring anything (D6).** Write `loadtest/SLO.md`:
  - the target p95 for a *complete run* (submission → final result) at a stated concurrency,
  - the justification against spec §1: an analyst's pre-print check, not a real-time path,
  - how it will be measured.

  **Merge it now.** The git timestamp proves the target came before the results.
  ```
  (after Prompt 0) Draft loadtest/SLO.md. Context: runs are multi-step agent runs (several LLM calls,
  tens of seconds); users are regulatory analysts checking labels before print (spec §1), not a
  real-time path. Propose an SLO as "p95 complete-run latency ≤ X s at C concurrent runs, measured
  with LLM replaced by a stub with realistic delay", with a justification paragraph, the SLI
  definition (submission timestamp to terminal status, measured client-side by polling), the error
  budget, and what counts as failure (timeouts, FAILED state, incomplete). Leave X and C as my decision
  with reasoning for 2-3 options.
  ```
- [ ] **N1.3 Write a decision record for the chunking strategy.** Write `docs/decisions/002-nishkal-chunking.md`. Chunk at clause or sub-clause level, never across clauses. Keep schedule and table rows whole. Each chunk's metadata records `regulation`, `clause_id`, `heading_path`, `doc_version` and `page`, plus a short "context header" (e.g. "FSS-AC-2018 › Schedule I › Protein") prepended before embedding. Explain how this helps the cross-regulation problem; that explanation becomes your L1 report section.

## Phase 2: real end-to-end (by end of week 2)

- [ ] **N2.1 Build the ingest CLI (D2, L1).** Running `python -m fssai_ingest build --corpus corpus/raw --out /data/index` does:
  - read → parse → clause-aware chunk → embed locally (sentence-transformers, model name from env) → FAISS (through LangChain),
  - **Idempotency:** stable chunk ids (hash of doc sha + clause id + text). Re-running with no changes does nothing.
  - **Partial re-embed:** `--reembed changed` re-embeds only chunks whose text or embedding model changed, without rebuilding everything.
  - **Freshness:** writes `index_manifest.json` with `built_at`, doc versions, chunk count, embedding model alias and throughput (chunks/s).
  ```
  (after Prompt 0) Implement fssai_ingest per Nishkal.md N2.1 and docs/decisions/002. Use pypdf or
  pdfminer.six for text, a clause-aware splitter (regex on clause numbering like "2.2.1", "(a)", "Schedule"
  headings, falling back to paragraph splits ≤ ~350 tokens), sentence-transformers via
  langchain-huggingface with EMBEDDING_MODEL from env, and FAISS via langchain-community. Store a
  docstore keyed by chunk_id with full Passage-compatible metadata (fssai_contracts.schemas.Passage).
  Implement --reembed changed using a sidecar table of chunk_id → (text_hash, model_alias).
  Write index_manifest.json. Tests: idempotent re-run (same chunk count, no new vectors), changed-text
  re-embed touches only that chunk, splitter keeps a schedule table row in one chunk.
  ```
- [ ] **N2.2 Implement `FaissRetriever` (the `Retriever` interface).**
  - `search(query, ctx, k, regulation)` filters by regulation.
  - `get_clause(regulation, clause_id)` is an exact metadata lookup.
  - It returns `Passage` objects with scores.
  - Test: the query "source of protein claim condition" must return your N1.1 Claims clause in the top-k. Write that test with the real index built from `corpus/`.
  ```
  (after Prompt 0) Implement fssai_retrieval.faiss_retriever:FaissRetriever satisfying
  fssai_contracts.interfaces.Retriever. Load the index from INDEX_DIR (env). search() supports a
  regulation filter (over-fetch then filter) and returns Passage with score; get_clause() does exact
  lookup on (regulation, clause_id) with normalisation of spacing/brackets. Add a from_registry()
  classmethod. Do NOT record steps (the agent records tool steps). Tests: filter works, clause lookup
  works, and a recall test that the §4.1 Claims clause from docs/eval1/section-4.1-passages.md is in
  top-5 for 3 phrasings of the question.
  ```
- [ ] **N2.3 Add the indexer container.** In `deploy/compose/indexer.yml`, add a one-shot `indexer` service that builds the index into a named volume on `docker compose up`, idempotently. The worker waits for `service_completed_successfully`. Tell Vismay the volume name and mount path.

## Phase 3: all requirements (weeks 3–4)

- [ ] **N3.1 Build the observability library and stack (D5).**
  - **Library:** `fssai_observability` provides `setup_logging(service)` (JSON lines with `run_id` and `correlation_id` when present), `setup_tracing(service)` (OTel SDK → OTLP to Jaeger, a no-op if `OTEL_EXPORTER_OTLP_ENDPOINT` is unset) and Prometheus helpers.
  - **Stack:** `deploy/compose/observability.yml` brings up Prometheus, Grafana (provisioned datasources and dashboards), Jaeger and cAdvisor.
  - **Dashboard:** `service-overview.json` shows p50/p95 latency, error rate, throughput, availability, and CPU and memory per container.
  - **Scaled workers:** scrape them via DNS service discovery, because `--scale worker=3` gives three targets behind one name.
  ```
  (after Prompt 0) Implement fssai_observability (setup_logging, setup_tracing, metrics helpers) and the
  observability Compose fragment per Nishkal.md N3.1. Prometheus must scrape every service including all
  replicas of worker (use dns_sd_configs on the compose service name). Provision Grafana datasources
  (Prometheus, Jaeger, Postgres read-only) and dashboards from observability/grafana/dashboards/.
  Build service-overview.json with p50/p95 (histogram_quantile), error rate, RPS, availability (up),
  container CPU/memory from cAdvisor. Everything configured via env; no hard-coded hosts outside compose.
  ```
- [ ] **N3.2 Expose freshness and throughput metrics (D2).** Expose `index_built_timestamp`, `index_chunks_total`, `index_doc_version_info` and `ingest_chunks_per_second` as metrics. The worker loads the manifest at start-up, so these work even though the indexer exits.
- [ ] **N3.3 Add caching (D7).** Write `docs/decisions/003-nishkal-caching.md` explaining which caches and why.
  - Cache query embeddings and retrieval results in Redis.
  - The key includes the index version, so a rebuild invalidates the cache automatically.
  - Expose hit and miss metrics.
  - Use `CACHE_ENABLED` to switch it on and off for the comparison.
- [ ] **N3.4 Build the stub LLM service (D6).** `services/stub_llm` is a small FastAPI app implementing an OpenAI-compatible `POST /v1/chat/completions`.
  - It returns canned JSON per `[prompt:<name>@...]` tag, using fixtures you copy from Namith's prompts once they exist, and a generic fallback until then.
  - Latency is configurable: a log-normal distribution with mean and p95 from env.
  - It reports realistic `usage` token counts.
  - `STUB_FAIL_RATE` and `STUB_DOWN=1` let Vismay demo the circuit breaker.
- [ ] **N3.5 Run the Locust load test (D6, A7).**
  - `loadtest/locustfile.py` submits a run and then **polls until it reaches a terminal state**. It reports full-run latency as a custom Locust event, not just the POST.
  - Step up the concurrency (e.g. 1, 2, 5, 10, 20) to find where p95 breaks the SLO.
  - Use the traces and dashboards to name the component responsible (queue wait? worker CPU? embedding? Postgres?).
  - Repeat with `docker compose up --scale worker=3`.
  - Write `loadtest/results/README.md` with RPS, p50, p95 against the target, met or not, the failure concurrency, the bottleneck and the effect of scaling.
  ```
  (after Prompt 0) Write loadtest/locustfile.py: each user POSTs a request from loadtest/payloads/*.json
  to /v1/runs with X-Client-Id per user (so rate limits don't skew results unless intended), then polls
  GET /v1/runs/{id} with backoff until state in {completed, failed}; fire a custom request event named
  "full_run" with the end-to-end latency and success flag. Add a loadtest/run_matrix.sh that runs headless
  at concurrency 1,2,5,10,20 for N minutes each, with --scale worker=1 and 3, saving CSVs to
  loadtest/results/<timestamp>/. Add a small script that turns the CSVs into a table of RPS/p50/p95 per
  setting against the SLO in loadtest/SLO.md.
  ```
- [ ] **N3.6 Measure the effect of caching.** Run the same Locust settings with the cache on and off. Report the change in p95 and in **cost per run**: get the per-run cost from `RunResult.totals` against the real provider for a few runs, and from Vismay's cost dashboard.

## Phase 4: hardening, extras, report

- [ ] **N4.1 Run the §4.1 rehearsal (you lead demo item 10).** On the real stack, check that the trace shows the claims condition being found *after* the labelling search, and that both regulations are cited.
- [ ] **N4.2 Write your report section** in `docs/report/retrieval-and-performance.md`.
- [ ] **N4.3 Write at least one incident entry** in `docs/incidents/`.
- [ ] **Extras** (pick in order):
  - [ ] hybrid BM25 + dense retrieval with a cross-encoder reranker, and measure the difference
  - [ ] recall@k against the eval set's supporting passages
  - [ ] claim-trigger map: a YAML file mapping claim wordings to Claims-regulation clause ids, used as a retrieval hint
  - [ ] Alertmanager SLO burn-rate alert

## CV line you'll be able to write
*"Built the retrieval and performance layer of a multi-agent regulatory-compliance service:
clause-aware chunking + local embeddings + FAISS with idempotent re-indexing, Redis caching, a
Prometheus/Grafana/Jaeger observability stack, and Locust load tests against a pre-declared p95
SLO, including bottleneck analysis under horizontal scaling."*

## Pitfalls
- Never let an LLM "recall" FSSAI clause numbers or thresholds. Quote only from the PDFs.
- Chunks that cut a schedule table in half are the most common reason the §4.1 case fails.
- Declaring the SLO after measuring scores zero for D6.
- The fake regulation text in `contracts/fakes.py` is placeholder text. Don't copy its numbers anywhere.
- **Mixed Windows/macOS team** (LLM_Context §8.8):
  - Your observability images and Python wheels must have `arm64` builds for teammates on Apple Silicon Macs.
  - cAdvisor under Docker Desktop sees less than it does on native Linux. Check that per-container CPU and memory actually show up on both OSs, and fall back to `docker stats`-based metrics if they don't.
  - Load-test results depend on the machine, so record the OS, CPU and Docker memory limit with every Locust run.

## Notes / log
(your notes here)
