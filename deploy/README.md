# deploy: how the stack is assembled

The root `docker-compose.yml` only `include:`s one fragment per owner from `compose/`, so nobody edits a
shared Compose file (LLM_Context §8.3). `docker compose up -d --build` from the repo root starts everything.

## compose/

| Fragment | Services | Owner |
|---|---|---|
| `api.yml` | `api` (FastAPI, port `API_HOST_PORT`, default 8000) | Vismay |
| `worker.yml` | `worker` (queue consumer; `--scale worker=N`) | Vismay |
| `web.yml` | `web` (nginx serving the web client and proxying the API, port `WEB_HOST_PORT`, default 8080) | Vismay |
| `redis.yml` | `redis` (queue, cache, rate-limit counters, breaker state) | Vismay |
| `postgres.yml` | `postgres` (runs and step traces, quarantine, feedback, quality scores) | Vismay |
| `indexer.yml` | `indexer` (one-shot job: builds the search index into the `index-data` volume) | Nishkal |
| `observability.yml` | `prometheus`, `grafana`, `jaeger`, `cadvisor`, `redis-exporter`, `postgres-exporter` | Nishkal |
| `stub-llm.yml` | `stub-llm` (OpenAI-compatible stand-in for load tests and the breaker demo) | Nishkal |

Every service has a health check. Why the boundaries fall where they do:
[decision 304](../docs/decisions/304-vismay-deployment-boundaries.md).

## postgres/init/

One SQL file per owner and table, named `NN-<owner>-<table>.sql`. Postgres runs them once, when the
`postgres-data` volume is first created. To apply a new file to an existing volume, run `docker compose down -v`
(this deletes the stored runs), then start the stack again.
