# Architecture

Owner: Vismay. This is the system as it is built and planned; status per box is in the table below.
Deployment boundaries (D3) are the dashed boxes: everything inside one is deployed, scaled and
restarted as one unit.

```
                         ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
   analyst / examiner ──▶   web  (nginx + static React build)        boundary 1: static, no state
                         └ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ┘
                                    │ same-origin /v1 (proxied)
                         ┌ ─ ─ ─ ─ ─▼─ ─ ─ ─ ─ ┐
                            api  (FastAPI)                            boundary 2: scales on HTTP load
                            gate: rate limit → validate → quarantine (D1)
                            202 {run_id} → poll (decision 301)
                         └ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ┘
                    save queued     │ enqueue job (RQ, decision 302)
             ┌──────────────────────┼──────────────────────┐
             ▼                      ▼                      │
   ┌ ─ ─ ─ ─ ─ ─ ─ ┐      ┌ ─ ─ ─ ─ ─ ─ ─ ┐                 │
     postgres                 redis                         │       boundaries 3 + 4: state
     runs + steps (D5)        queue · cache                 │
     quarantine (D1)          rate limits                   │
     feedback (L6)            breaker state (A5)            │
   └ ─ ─ ─ ─ ─ ─ ─ ┘      └ ─ ─ ─ ─│─ ─ ─ ┘                 │
             ▲                     │ job                   │
             │          ┌ ─ ─ ─ ─ ─▼─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐  │
             └─ result     worker × N  (python -m fssai_worker)      boundary 5: scales on run load (A7)
                           guardrails → classifier → [researcher ⇄ verifier] ×≤3 → router → output filter
                           LLM gateway: timeouts · retry · breaker · fallback · cost (A5, L5)
                        └ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ┘
                                 │ read-only     │ OpenAI-compatible HTTP
                       FAISS index volume      LLM provider (free tier)  |  stub-llm (load tests, D6)
                       ▲ built by indexer (one-shot job, boundary 6)
```

Observability (boundary 7): Prometheus scrapes every service (`/metrics`; workers on their own port),
Grafana dashboards, Jaeger traces, cAdvisor for per-container resources. Correlation ids join logs,
traces and steps across the boundaries.

## Why these boundaries

| Boundary | Scales on | Fails how | Released when | Resource profile |
|---|---|---|---|---|
| web | nothing (static) | serves files only | UI changes | tiny |
| api | HTTP requests | a crash loses no run: runs are saved before they are queued | API or gate changes | light CPU |
| worker | runs in flight (`--scale worker=N`) | a crashed worker loses one job, which the RunStore shows as not finished | agent, prompt, gateway changes | CPU + memory (embeddings), long requests |
| redis / postgres | — | state survives api and worker restarts | rarely | memory / disk |
| indexer | corpus changes | exits; workers wait for it | corpus or chunking changes | heavy, short-lived |
| stub-llm | load tests | replaces the provider so tests measure our system | with the load test | light |

The API and the workers are separate because they scale on different things: one is fast HTTP, the
other is tens of seconds of agent work per run. Putting them in one container would make every API
replica carry the model and index memory, and a slow run could starve request handling.

## Status (2026-10-25)

| Part | State |
|---|---|
| API, worker, queue, Postgres run store, gateway, web client | built; running in Compose (`docker compose up -d --build`) |
| Compose stack, nginx for web, smoke test, clean-clone test, CI | built and verified: clean `.env.example` boots, `--scale worker=3` works |
| Tracing across the queue | one Jaeger trace from the API's submit span to the worker's run |
| Corpus, index, hybrid retriever, observability stack, stub LLM | Nishkal's, merged; real retriever verified in the stack |
| Gate, verifier, router | fakes until Vihaan's land (skeletons + conformance tests ready) |
| Classifier, researcher, LangGraph pipeline, guardrails, prompts | fakes until Namith's land (skeletons + conformance tests ready) |

Locally without Docker, `RUN_DISPATCH=inline` runs jobs inside the API process (decision 302).
