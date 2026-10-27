# Stub LLM (`apps/stub_llm`)

An OpenAI-compatible stand-in for the LLM provider. Owner: Nishkal · task N3.4.

- **Load tests (D6)** use it so they measure our system, not a free tier's rate limits.
- **The circuit-breaker demo (A5, #8)** switches it down at runtime.

```
POST /v1/chat/completions   canned reply by prompt tag, after a log-normal delay, with token usage
GET  /v1/models
GET|POST /admin/faults      read or change faults at runtime: {"down": "1"|"0"|"hang", "fail_rate": 0.2, ...}
GET  /healthz  /readyz  /metrics
```

| Env | Default | |
|---|---|---|
| `STUB_LATENCY_MEAN_S` / `STUB_LATENCY_P95_S` | 1.5 / 4 | log-normal delay with this mean and p95 (`latency.py` derives the parameters) |
| `STUB_DOWN` | `0` | `1` answers 503; `hang` never answers in time (timeouts) |
| `STUB_FAIL_RATE` / `STUB_RATE_LIMIT_RATE` | 0 / 0 | share of calls answered 500 / 429 (`Retry-After: 1`) |
| `STUB_FIXTURES_DIR` | package `fixtures/` | replies per prompt tag (see `fixtures/README.md`) |
| `STUB_SEED` | random | fixed seed for repeatable delays and faults |

Point the gateway at it: `LLM_BASE_URL=http://stub-llm:8080/v1`, `LLM_MODEL=stub`. From the host it listens
on `localhost:${STUB_LLM_HOST_PORT:-8081}`:

```bash
curl -X POST http://localhost:8081/admin/faults -H "content-type: application/json" -d "{\"down\": \"1\"}"   # provider down
curl -X POST http://localhost:8081/admin/faults -H "content-type: application/json" -d "{\"down\": \"0\"}"   # recovered
```

```bash
<venv-python> -m pip install -e "apps/stub_llm[test]"
<venv-python> -m pytest apps/stub_llm -q   # includes the real GatewayLLMClient opening its breaker against it
<venv-python> -m uvicorn fssai_stub_llm.app:create_app --factory --port 8081   # run locally
```
