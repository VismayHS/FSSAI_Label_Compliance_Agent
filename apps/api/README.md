# api

The HTTP front door (A4, F1, F8). Owner: Vismay, except `app/routers/feedback.py` and `app/routers/quarantine.py`
(Vihaan). The full contract is in LLM_Context §7, and FastAPI publishes it at `/docs`.

| File | What |
|---|---|
| `app/main.py` | App factory: builds the gate, run store and dispatcher from the registry, and mounts every router |
| `app/routers/runs.py` | `POST /v1/runs` (client id, size limit, gate, then enqueue), `GET /v1/runs`, `GET /v1/runs/{id}`, `GET /v1/runs/{id}/trace` |
| `app/routers/health.py` | `/healthz`, `/readyz` (which also says which parts are real and which are stand-ins), `/metrics` |
| `app/routers/*.py` | Any module with a `router` is mounted automatically, so teammates add routes without editing `main.py` |
| `app/observability.py` | Correlation ids, structured access logs, HTTP metrics |
| `app/models.py` | HTTP-only response shapes; request and run data use the contracts' models |

```bash
<venv-python> -m uvicorn app.main:create_app --factory --env-file .env --port 8000   # inline mode, no Docker
<venv-python> -m pytest apps/api -q
```
