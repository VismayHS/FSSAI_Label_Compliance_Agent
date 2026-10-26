# fssai_llm_gateway

The production `LLMClient` (A5, L5). Every agent's LLM call goes through it. Owner: Vismay.
Switch it on with `IMPL_LLM=fssai_llm_gateway.client:GatewayLLMClient`.

| File | What |
|---|---|
| `fssai_llm_gateway/client.py` | `GatewayLLMClient`: OpenAI-compatible calls with a per-call timeout capped by the run's deadline, bounded retries with exponential backoff and jitter (honours `Retry-After`), a fallback model, JSON mode, and tokens and cost recorded as an `llm` step |
| `fssai_llm_gateway/breaker.py` | Circuit breaker: after `BREAKER_FAILURE_THRESHOLD` failures the provider is skipped for `BREAKER_COOLDOWN_S`. State lives in memory, or in Redis so every worker shares it |
| `fssai_llm_gateway/metrics.py` | Prometheus metrics: calls, retries, tokens, cost |
| `fssai_llm_gateway/demo.py` | Demo #8: `python -m fssai_llm_gateway.demo` shows the breaker opening, failing fast and recovering against the stub LLM |

Configuration is env only (`LLM_*`, `LLM_FALLBACK_*` and `BREAKER_*` in `.env.example`). Provider URLs, keys and
model ids never appear in the repo or in traces: a step records only the provider alias, `primary` or `fallback`.

```bash
<venv-python> -m pytest packages/llm_gateway -q      # no network: HTTP is mocked
```
