# FSSAI Label Compliance Agent

A multi-agent service that checks a proposed packaged-food label against two FSSAI regulations
(Labelling & Display 2020, Advertising & Claims 2018). For each requirement it returns a finding with
citations to regulation and clause, and routes the label to `clear-for-print`, `revise-and-recheck` or
`regulatory-review`. **It never approves a label for print; a regulatory affairs professional decides.**

Mini Project 10 for UE24AM342AA5, ML System Design & AgentOps (Dept of CSE (AI & ML), PESU).

| Team | Workstream |
|---|---|
| Nishkal | Knowledge & Performance: corpus, retrieval, caching, observability, SLO + load testing |
| Namith | Agent Reasoning: LangGraph agents, prompts, guardrails, agent metrics |
| Vihaan | Trust & Evaluation: data contract + validation, verifier agent, routing, evaluation, feedback |
| Vismay | Platform & Integration: API, queue, workers, LLM gateway, Docker Compose, tracing, web client |

## Run it from a clean clone

**You need:** Git, and Docker Desktop with Compose v2.20 or later and at least 8 GB of memory for Docker.
Windows (WSL 2 backend), macOS (Intel or Apple Silicon) and Linux all work. Python 3.11+ is needed only
for the helper scripts (smoke test, demos), and they use nothing but the standard library.

```bash
git clone https://github.com/VismayHS/FSSAI_Label_Compliance_Agent.git
cd FSSAI_Label_Compliance_Agent
cp .env.example .env              # Windows PowerShell: Copy-Item .env.example .env
docker compose up -d --build      # first build takes ~5-10 minutes; later starts take seconds
```

Then open the web client at **http://localhost:8080**, press **Check the §4.1 example**, and open the
run's **Trace** tab. Check that everything works end to end:

```bash
python tools/scripts/smoke.py           # (python3 on macOS) readiness, one run to completion, one rejected request
```

With `.env` copied unchanged, every agent runs on the shared **fakes**, so the regulation text you see
is marked `[PLACEHOLDER, NOT REAL REGULATION TEXT]`. The next section switches on the real parts.

### Configure the real stack (`.env`)

| To use | Set in `.env` |
|---|---|
| A real LLM (any OpenAI-compatible free tier) | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` from your provider, and `IMPL_LLM=fssai_llm_gateway.client:GatewayLLMClient`. Set `LLM_PRICE_*_PER_1K` to get real costs. |
| Real retrieval over the FSSAI regulations | `EMBEDDING_MODEL` = a small local sentence-transformers model (MiniLM-class, see decision 002), and `IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever`. The `indexer` service builds the index on the next `up`. |
| Tracing in Jaeger | `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318` |
| Each teammate's component, once merged | its `IMPL_*` line (examples in `.env.example`) |

Apply changes with `docker compose up -d` (it recreates only what changed). Credentials, endpoints and
model ids live only in `.env`, which git ignores (D4; `python tools/scripts/audit_secrets.py` checks the repo).

### What runs where

| | URL |
|---|---|
| Web client | http://localhost:8080 |
| API and its interactive docs (OpenAPI) | http://localhost:8000/docs |
| Grafana dashboards (service overview, cost; agents and quality as they land) | http://localhost:3000 |
| Prometheus (targets, SLO alerts) | http://localhost:9090 |
| Jaeger traces | http://localhost:16686 |
| Stub LLM (load tests, breaker demo) | http://localhost:8081 |

A port already taken on your machine? Change `API_HOST_PORT`, `WEB_HOST_PORT`, `GRAFANA_HOST_PORT`,
`PROMETHEUS_HOST_PORT`, `JAEGER_UI_HOST_PORT` or `STUB_LLM_HOST_PORT` in `.env`.

### Submit a label without the web client

```bash
curl -s -X POST http://localhost:8000/v1/runs -H "Content-Type: application/json" -H "X-Client-Id: me" \
     -d @infra/loadtest/payloads/protein-claim-low.json                    # 202 {run_id, status_url, trace_url}
curl -s http://localhost:8000/v1/runs/<run_id>                       # poll until state is completed or failed
curl -s http://localhost:8000/v1/runs/<run_id>/trace                 # every step, passage, prompt, latency, cost
```

A malformed body gets `422` with field-level errors and a `quarantine_id`, and no run is created. The
full HTTP contract is in [docs/contexts/LLM_Context.md §7](docs/contexts/LLM_Context.md) and at `/docs`.

### Demos and checks

| What | Command (or `make <target>` on macOS/Linux) |
|---|---|
| Smoke test (demo #1) | `python tools/scripts/smoke.py` · `make smoke` |
| Fresh clone → up → smoke, isolated from your running stack | `python tools/scripts/clean_clone_test.py` · `make clean-clone` |
| Circuit breaker opens, fails fast, recovers (demo #8) | `docker compose exec worker python -m fssai_llm_gateway.demo` · `make demo-breaker` |
| Scale the workers (A7) | `docker compose up -d --scale worker=3` |
| Load test against the declared SLO (demo #9) | see [infra/loadtest/results/README.md](infra/loadtest/results/README.md) |
| Cost per 100 runs and the largest driver (L5) | `python tools/scripts/cost_report.py` · `make cost` |
| Every package's tests | `python tools/scripts/test_all.py` (in the dev `.venv`) · `make test` |
| No secrets in the repo (D4) | `python tools/scripts/audit_secrets.py` · `make audit` |
| Logs · status · stop | `docker compose logs -f` · `docker compose ps` · `docker compose down` |

### When something goes wrong

- **`indexer` exited 1:** `EMBEDDING_MODEL` is empty or the model could not download. The rest of the stack
  still runs (on the fake retriever); set it in `.env` and run `docker compose up -d` again.
- **`/readyz` says not ready:** `docker compose ps` shows which dependency is unhealthy; `docker compose logs <service>`.
- **A teammate changed a table:** Postgres creates tables only on a new volume. `docker compose down -v`
  recreates it (and deletes stored runs).
- **`env file .env not found`:** run the `cp .env.example .env` step first.

Design: [architecture and deployment boundaries](docs/architecture.md) · [decision records](docs/decisions/README.md)
· [incident log](docs/incidents/) · [`.env.example`](.env.example). The runbook, data contract, agent
topology and eval set join this list as their owners merge them.

## Develop (team)

Everyone works on **their own branch** (`nishkal`, `namith`, `vihaan`, `vismay`) and keeps their own
commit history. Nobody commits or pushes to `main`; work reaches it only through PRs, which CI checks.
Read [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit.

1. Set your git identity to your GitHub account, then clone and run the setup script with your name:
   ```bash
   git config --global user.name  "Your Name"
   git config --global user.email "you@example.com"     # the email on your GitHub account
   git clone https://github.com/VismayHS/FSSAI_Label_Compliance_Agent.git
   cd FSSAI_Label_Compliance_Agent
   python tools/scripts/setup_dev.py <your-name>             # nishkal | namith | vihaan | vismay
   ```
   It switches you to your branch, turns on the git hooks, creates `.venv` with the contracts, your own
   packages and the API, runs the tests and creates `.env`.
2. Read [docs/contexts/LLM_Context.md](docs/contexts/LLM_Context.md), then your own `docs/contexts/<Name>.md` from *Start here*.
   AI coding assistants pick up [AGENTS.md](AGENTS.md) (Claude Code also loads [CLAUDE.md](CLAUDE.md)).

Without Docker, the API also runs on its own on the fakes (inline mode, no Redis or Postgres):
```bash
.venv/Scripts/python -m uvicorn app.main:create_app --factory --env-file .env --port 8000   # macOS: .venv/bin/python
npm --prefix apps/web ci && npm --prefix apps/web run dev                          # http://localhost:5173
```

## Repository map

Six top-level folders, each with a README that says what is in it and who owns it.

```text
.
├── apps/                what runs as a container
│   ├── api/             FastAPI: submit, poll, trace, health (+ feedback and quarantine routes)
│   ├── worker/          queue consumer that runs the agent pipeline (--scale worker=N)
│   ├── web/             the analyst's web client (React + Vite, served by nginx)
│   └── stub_llm/        OpenAI-compatible stand-in LLM for load tests and the breaker demo
├── packages/            Python packages, one per component, each with its own pyproject.toml and tests
│   ├── contracts/       the shared seams: schemas, interfaces, fakes, reference pipeline, conformance checks
│   ├── agents/ prompts/ guardrails/            classifier, researcher, LangGraph pipeline; versioned prompts
│   ├── ingest/ retrieval/ observability/       index build, hybrid retrieval, logs/tracing/metrics helpers
│   ├── gate/ verification/                     ingestion gate; verifier agent and router
│   ├── llm_gateway/ run_store/                 LLM client with retries, breaker and cost; Postgres run store
│   └── eval/            evaluation set, runner, metrics and live scoring
├── infra/               how it is deployed and observed
│   ├── compose/         one Compose fragment per owner (included by docker-compose.yml)
│   ├── postgres/init/   one SQL file per owner and table
│   ├── observability/   Prometheus rules and Grafana dashboards
│   └── loadtest/        the declared SLO, the Locust load test and its results
├── data/corpus/         the two FSSAI regulations (PDFs), their provenance, claim-trigger map
├── docs/                architecture, agent topology, runbook, data contract, decisions, incidents, report
│   ├── contexts/        the shared project context and each team member's plan and progress
│   └── course/          the course documents (spec, glossary, index)
├── tools/
│   ├── scripts/         setup, smoke test, clean-clone test, tests, secrets audit, cost report, report builder
│   └── skills/          shared AI-assistant skills (our own, plus pinned vendored copies)
├── docker-compose.yml   the whole stack: includes the fragments in infra/compose/
├── .env.example         every setting, one section per owner (copy to .env; .env is never committed)
├── Makefile             shortcuts for the commands above (each is also a plain command)
└── .github/ .githooks/  CI, CODEOWNERS and PR template; the git hooks that enforce the branch rules
```

| Path | Owner |
|---|---|
| [`apps/`](apps/) | api, worker, web: Vismay · stub_llm: Nishkal · api feedback and quarantine routes: Vihaan |
| [`packages/`](packages/) | per package: see [packages/README.md](packages/README.md); `contracts/` is shared, stewarded by Vismay |
| [`infra/`](infra/) | one Compose fragment and one SQL file per owner; `observability/` and `loadtest/`: Nishkal (one dashboard file per owner) |
| [`data/corpus/`](data/corpus/) | Nishkal |
| [`docs/`](docs/) | per file: see [docs/README.md](docs/README.md); each person edits only their own `contexts/<Name>.md` |
| [`tools/`](tools/), [`.github/`](.github/), root files | Vismay |

