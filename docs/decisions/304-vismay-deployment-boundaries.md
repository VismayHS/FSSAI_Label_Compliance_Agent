# 304 · Deployment boundaries: one Compose service per scaling, failure and release profile

**Status:** accepted · **Owner:** Vismay · **Requirements:** D3, A7, A4, A5

## Context
D3 asks for at least four Compose services started by one `docker compose up`, each with a health check,
and for the boundaries to be justified by scaling, failure isolation, independent release and resource
profile. A *deployment boundary* is everything deployed, scaled and restarted as one unit
(`docs/course/00_GLOSSARY.pdf`). The pieces differ a lot: HTTP handling takes milliseconds, an agent run takes
tens of seconds and holds an embedding model and the index in memory, the index build is a heavy job that
runs only when the corpus changes, and the load test must not pay a real provider.

## Options
| Option | For | Against |
|---|---|---|
| One app container (API + pipeline + static UI) | Fewest moving parts | Every HTTP replica carries the model and index memory; a slow run starves request handling; `--scale` scales both or neither (A7 cannot be measured); a UI fix restarts the agents |
| API + worker together, separate data stores | Simple, still a queue | Same scaling and memory problem; a worker crash takes the API down |
| **API, worker, web, indexer, stub-llm as separate services; Redis and Postgres for state** | Each scales and fails on its own; the worker is the only heavy image | More images to build; the queue and the run store become required infrastructure |
| A service per agent (classifier, researcher, verifier containers) | Independent scaling per agent | Network hops and serialisation inside one run for no measured benefit; the agents share one budget and one trace, which the hand-off schemas already separate in code (A2) |

## Decision
Eleven services (plus two metric exporters), one `docker compose up -d --build`, each owner's services in
their own fragment under `deploy/compose/`, included by the root `docker-compose.yml`:

| Service | Image | Scales on | Fails how | Released when | Resources |
|---|---|---|---|---|---|
| `web` | nginx, static build | nothing (static) | serves files; proxies `/v1` to the API | UI changes | ~75 MB image, tiny |
| `api` | Python, gate + run store, no agents | HTTP requests | runs are saved before they are queued, so a crash loses none | API or gate changes | ~300 MB, light CPU |
| `worker` × N | Python, every pipeline package, CPU torch | runs in flight (`--scale worker=N`) | a crash loses one job; the run store shows it unfinished | agent, prompt, retriever, gateway changes | ~2.3 GB, CPU + memory |
| `redis` | redis | — | append-only file: queued jobs survive a restart | rarely | small memory |
| `postgres` | postgres | — | volume: runs, steps, quarantine, feedback survive restarts | schema changes | disk |
| `indexer` | Python, ingest | one-shot | exits; the worker waits for it but still starts if it fails (`required: false`) | corpus or chunking changes | heavy, short-lived |
| `stub-llm` | Python | load tests, breaker demo | stands in for the provider | with the load test | light |
| prometheus, grafana, jaeger, cadvisor | upstream | — | observation only; nothing depends on them | rarely | moderate |

- **Stateless workers (A7).** Everything a run needs is in the job payload; everything it produces goes to
  Postgres; the circuit breaker lives in Redis; the index and model are read-only volumes. No worker has
  a `container_name` or host port, so replicas are interchangeable and Prometheus finds each by DNS.
- **The API image carries no agent code.** In Compose the API only enqueues (`RUN_DISPATCH=queue`), and it
  builds the pipeline only in inline mode, so it stays small and starts in seconds.
- **The worker image carries every pipeline package**, so switching a seam with an `IMPL_*` variable is an
  `.env` change and a restart, never a different image.
- **Boot order by health, not by sleep.** `depends_on: condition: service_healthy` for Redis and Postgres;
  the indexer is `service_completed_successfully` with `required: false`, so a missing `EMBEDDING_MODEL`
  degrades retrieval instead of stopping the whole stack from booting (demo #1 is worth everything).

## Consequences
- Measured on 2026-10-25 (Windows, Docker Desktop): first `docker compose up -d --build` about 5 minutes,
  later starts seconds; `--scale worker=3` spread six runs over three replicas, and Prometheus listed all
  three worker targets with no config change.
- The worker image is large because of torch; it builds once and is cached. Teammates' heavy dependencies
  land in the worker image only.
- Postgres creates its tables only when its volume is new; a schema change needs
  `docker compose down -v` (drops stored runs) or applying the file by hand (see the SQL file's header).
