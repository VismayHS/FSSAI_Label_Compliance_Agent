# services: what runs

| Service | What | Owner |
|---|---|---|
| [`api/`](api/) | FastAPI: submit a check (202 and a run id), poll it, read its trace; health, readiness, metrics | Vismay (feedback and quarantine routes: Vihaan) |
| [`worker/`](worker/) | Takes runs off the Redis queue and executes the agent pipeline; scale with `--scale worker=N` | Vismay |
| [`web/`](web/) | The analyst's web client (React + Vite) | Vismay |
| [`stub_llm/`](stub_llm/) | OpenAI-compatible stand-in LLM for load tests and the breaker demo | Nishkal |

How they are deployed together: [`../deploy/`](../deploy/).
