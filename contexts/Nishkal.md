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
3. contracts/fssai_contracts/*.py  (schemas, interfaces, context, fakes, pipeline, registry, conformance)

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
- My package skeletons already exist (day-0 baseline): fill them in, keep their class names and
  signatures, and make each conformance test (fssai_contracts.conformance) pass, then delete its xfail marker.
- Git: I work only on my own branch `nishkal` (check `git branch --show-current`). Never commit or
  push to main or a teammate's branch, never force-push, never --no-verify, merge origin/main
  (never rebase). No Co-Authored-By/"Generated with" lines. Commit or push only when I ask.
Summarise my current task in 3 lines, then wait for my go.
```

---

## Start here: your day-0 baseline

Your packages already exist as **skeletons**: installable, tested, wired to the right `IMPL_*` names,
and empty. Vismay scaffolded them on 2026-10-24 so all four of us start from the same working base.
They are yours like everything else in your paths: change anything except a seam's class name and
method signatures, which other people's code and `.env` depend on.

| Package | What you fill in | Its contract test | Task |
|---|---|---|---|
| `libs/retrieval` | `fssai_retrieval.faiss_retriever:FaissRetriever` | `check_retriever` | N2.2 |
| `libs/ingest` | `python -m fssai_ingest build ...` (CLI options fixed) | CLI options test | N2.1 |
| `libs/observability` | `fssai_observability.setup_logging` / `setup_tracing` | JSON logs, tracing no-op | N3.1 |

**How a skeleton tells you you're done.** Every skeleton method raises `NotImplementedError("<task>: ...")`.
Its test calls the shared check in `contracts/fssai_contracts/conformance.py`, marked
`xfail(raises=NotImplementedError, strict=True)`. That gives three states:

| `pytest libs/retrieval libs/ingest libs/observability -q` says | Meaning | Do |
|---|---|---|
| `xfailed` | not built yet | build it |
| `FAILED` with an `AssertionError` | built, but it breaks a contract edge (the message says which) | fix it |
| `FAILED` with `XPASS(strict)` | built and conforming | delete the `xfail` line: from now on it guards you |

**Switching on.** When a seam's contract test passes without its marker, set its `IMPL_*` variable in
your `.env`, run `pytest contracts -q` and a local run (LLM_Context §7) with it on, add it as a comment
in your `.env.example` section, and tell Vismay. Until then everyone else keeps using the fake.

Each package README lists its files and commands. `conformance.sample_request()` gives you a valid
§4.1-style request for your own tests.

---

## Phase 0: setup (days 1–2)

- [ ] **N0.1 Set up and prove the loop.** Clone the repo and run `python scripts/setup_dev.py nishkal` (CONTRIBUTING.md §2). Your package skeletons already exist (see *Start here*), so this is only:
  1. Check that setup ended with your tests showing `xfailed` and nothing `failed`.
  2. Read the three package READMEs and `fssai_contracts/conformance.py` (`check_retriever`).
  3. Make one small commit of your own on `nishkal` (e.g. a dated line in *Notes / log* below), `git push`, and open your first PR (`main` ← `nishkal`), so you've done the whole loop once.
- [x] **N0.2 Get the corpus and propose a product category.**
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

- [x] **N1.1 Find the §4.1 passages (the reference answer).** Read the two regulations yourself; the LLM only helps you search. Find:
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
- [x] **N1.2 Declare the SLO before measuring anything (D6).** Write `loadtest/SLO.md`:
  - the target p95 for a *complete run* (submission → final result) at a stated concurrency,
  - the justification against spec §1: an analyst's pre-print check, not a real-time path,
  - how it will be measured.

  **Commit and push it to `nishkal` now, and get it into `main` the same day.** The commit timestamp proves the target came before the results.
  ```
  (after Prompt 0) Draft loadtest/SLO.md. Context: runs are multi-step agent runs (several LLM calls,
  tens of seconds); users are regulatory analysts checking labels before print (spec §1), not a
  real-time path. Propose an SLO as "p95 complete-run latency ≤ X s at C concurrent runs, measured
  with LLM replaced by a stub with realistic delay", with a justification paragraph, the SLI
  definition (submission timestamp to terminal status, measured client-side by polling), the error
  budget, and what counts as failure (timeouts, FAILED state, incomplete). Leave X and C as my decision
  with reasoning for 2-3 options.
  ```
- [x] **N1.3 Write a decision record for the chunking strategy.** Write `docs/decisions/002-nishkal-chunking.md`. Chunk at clause or sub-clause level, never across clauses. Keep schedule and table rows whole. Each chunk's metadata records `regulation`, `clause_id`, `heading_path`, `doc_version` and `page`, plus a short "context header" (e.g. "FSS-AC-2018 › Schedule I › Protein") prepended before embedding. Explain how this helps the cross-regulation problem; that explanation becomes your L1 report section.

## Phase 2: real end-to-end (by end of week 2)

- [x] **N2.1 Build the ingest CLI (D2, L1).** Running `python -m fssai_ingest build --corpus corpus/raw --out /data/index` does:
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
- [x] **N2.2 Implement `FaissRetriever` (the `Retriever` interface).**
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
- [x] **N2.3 Add the indexer container.** In `deploy/compose/indexer.yml`, add a one-shot `indexer` service that builds the index into a named volume on `docker compose up`, idempotently. The worker waits for `service_completed_successfully`. Tell Vismay the volume name and mount path.

## Phase 3: all requirements (weeks 3–4)

- [x] **N3.1 Build the observability library and stack (D5).**
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
- [x] **N3.2 Expose freshness and throughput metrics (D2).** Expose `index_built_timestamp`, `index_chunks_total`, `index_doc_version_info` and `ingest_chunks_per_second` as metrics. The worker loads the manifest at start-up, so these work even though the indexer exits.
- [x] **N3.3 Add caching (D7).** Write `docs/decisions/003-nishkal-caching.md` explaining which caches and why.
  - Cache query embeddings and retrieval results in Redis.
  - The key includes the index version, so a rebuild invalidates the cache automatically.
  - Expose hit and miss metrics.
  - Use `CACHE_ENABLED` to switch it on and off for the comparison.
- [x] **N3.4 Build the stub LLM service (D6).** `services/stub_llm` is a small FastAPI app implementing an OpenAI-compatible `POST /v1/chat/completions`.
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
  "full_run" with the end-to-end latency and success flag. Add a loadtest/run_matrix.py (Python, so it
  runs on Windows and macOS alike) that runs Locust headless
  at concurrency 1,2,5,10,20 for N minutes each, with --scale worker=1 and 3, saving CSVs to
  loadtest/results/<timestamp>/. Add a small script that turns the CSVs into a table of RPS/p50/p95 per
  setting against the SLO in loadtest/SLO.md.
  ```
- [ ] **N3.6 Measure the effect of caching.** Run the same Locust settings with the cache on and off. Report the change in p95 and in **cost per run**: get the per-run cost from `RunResult.totals` against the real provider for a few runs, and from Vismay's cost dashboard.

## Phase 4: hardening, extras, report

- [ ] **N4.1 Run the §4.1 rehearsal (you lead demo item 10).** On the real stack, check that the trace shows the claims condition being found *after* the labelling search, and that both regulations are cited.
- [x] **N4.2 Write your report section** in `docs/report/retrieval-and-performance.md`.
- [x] **N4.3 Write at least one incident entry** in `docs/incidents/`.
- [ ] **Extras** (pick in order):
  - [x] hybrid BM25 + dense retrieval with a cross-encoder reranker, and measure the difference
  - [x] recall@k against the eval set's supporting passages
  - [x] claim-trigger map: a YAML file mapping claim wordings to Claims-regulation clause ids, used as a retrieval hint
  - [x] Alertmanager SLO burn-rate alert

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

**2026-10-25: Phases 0–3 built, tested on the real corpus; stack-level measurements still to run.**

Done (details in the files named):
- **Corpus:** both FSSAI compendia in `corpus/raw/` (fssai.gov.in was unreachable, so archived copies of
  the official URLs were used; incident + decision 004), `sources.yaml`, generated `manifest.json`,
  `tools/manifest.py`, `tools/grep_pdf.py`.
- **Category:** breakfast cereals, *proposed* in decision 001. Post it in the group chat for the team
  to confirm. `.env.example` now says `CORPUS_CATEGORIES=breakfast-cereals`.
- **§4.1 passages:** `docs/eval1/section-4.1-passages.md`, 12 passages quoted from the PDFs. Key
  findings for Vihaan and Namith: the condition is **% of RDA** (Schedule I item 11, substituted
  text); **no protein RDA value exists in the corpus** (both regulations defer to ICMR). This needs a
  team decision before the test values are final (options in that file).
- **SLO:** `loadtest/SLO.md`: p95 ≤ 60 s at 5 concurrent, ≤ 1 % failed. **Commit it on its own
  first and get it into `main` today** (the timestamp is the evidence).
- **Ingest + retrieval:** clause-aware chunker (425 chunks, 52 superseded; table rows whole),
  idempotent build with partial re-embed, hybrid FAISS + BM25 + claim hints, exact `get_clause`.
  Real-model recall: hit@5 = 1.0, MRR 0.823 (dense alone 0.857 / 0.736). `check_retriever` passes; the
  xfail markers are gone.
- **Observability:** library (JSON logs, OTel, trace propagation helpers, freshness gauges); Compose
  stack (Prometheus with DNS discovery for scaled workers, Grafana with provisioned datasources and the
  `service-overview` dashboard, Jaeger, cAdvisor, Redis and Postgres exporters); SLO burn-rate rules.
- **Stub LLM:** `services/stub_llm`, tested behind Vismay's real `GatewayLLMClient` (the breaker opens).
- **Load-test tooling:** `loadtest/locustfile.py` (`full_run` = submit → terminal),
  `run_matrix.py`, `summarize.py`, payloads. Smoke-tested against the API inline on fakes.
- **Docs:** decisions 001–004, report section, 3 incidents.

Not done yet:
- N0.1: first commit, push and PR (your own git step).
- N3.5/N3.6/N4.1: need the full stack (root `docker-compose.yml` from Vismay). Then run
  `loadtest/run_matrix.py` and fill in `loadtest/results/README.md` and section 4 of the report.
- Docker images (`libs/ingest/Dockerfile`, `services/stub_llm/Dockerfile`) are written and the
  Compose fragments validate with `docker compose config`, but the images were **not built** here (the
  Docker daemon was not running). Build them once: `docker compose build indexer stub-llm`.
- Stub fixtures per prompt: copy real responses once Namith's prompt names exist
  (`services/stub_llm/fssai_stub_llm/fixtures/README.md`).

Tell Vismay (worker/compose):
- worker `depends_on: indexer: {condition: service_completed_successfully}`; mount `index-data:/data/index:ro`
  and `hf-cache:/data/hf-cache:ro`; env `INDEX_DIR=/data/index`, `HF_HOME=/data/hf-cache`, `HF_HUB_OFFLINE=1`.
  The volumes are declared in `deploy/compose/indexer.yml`: reference them, don't redeclare them.
- The worker image needs `contracts`, `libs/observability` and `libs/retrieval[embeddings]` with CPU torch
  (`--index-url https://download.pytorch.org/whl/cpu`, as in `libs/ingest/Dockerfile`), or every
  replica pulls ~2 GB of CUDA wheels.
- Prometheus expects the API's `/metrics` on `api:8000` and the worker's on `worker:9100`.
- Include my fragments in the root `docker-compose.yml`: `indexer.yml`, `stub-llm.yml`, `observability.yml`.
- Call `setup_logging(...)` / `setup_tracing(...)` at start-up; carry the trace with
  `inject_trace_context()` / `attach_trace_context()` across the queue.

Running locally (Windows): HuggingFace downloads failed TLS verification behind the antivirus (incident).
The model is cached in `data/hf-cache`. Use `HF_HOME=<repo>/data/hf-cache` and `HF_HUB_OFFLINE=1`.

**2026-10-25 (written by Vismay, noted here as the team rule asks): two things found while bringing up Compose.**
- **Fixed for you:** `libs/ingest/fssai_ingest/chunker.py` line 255 put a backslash inside an f-string
  expression. That is a `SyntaxError` before Python 3.12, so the indexer container (`python:3.11-slim`)
  exited 1 at import; the tests passed only because the local `.venv` is Python 3.13. The regex now runs on
  the line above. Logic and output are unchanged, and all 32 ingest tests pass. CI now compiles every file
  on Python 3.11, so this can't recur unnoticed.
- **Your call:** with `EMBEDDING_MODEL=` empty in `.env.example`, a clean clone's indexer exits 1. The worker
  still starts, because `deploy/compose/worker.yml` makes the indexer dependency `required: false`, but the
  real retriever then has no index. Please decide what a clean clone should get: the real model name in
  your section, or `hashing`, or a README step. Until then the demo machine's `.env` needs
  `EMBEDDING_MODEL` set before `docker compose up`.
- **Decided (Vismay, 2026-10-25, on the team's behalf):** a clean clone gets `EMBEDDING_MODEL=hashing` in your
  `.env.example` section. It builds offline, keeps model names out of the repo (D4), and the hybrid retriever
  still runs BM25 + claim hints. The real MiniLM-class model is set in the team's shared `.env` for the demo and
  for your recall numbers. Change it back if you disagree; it is your section.

