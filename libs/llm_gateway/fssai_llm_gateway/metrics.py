"""Prometheus metrics for the gateway. Exposed by whichever process imports it (API, worker)."""
from __future__ import annotations

from prometheus_client import Counter, Gauge

LLM_CALLS = Counter("fssai_llm_calls_total", "Logical LLM calls by outcome",
                    ["agent", "step", "model_alias", "outcome"])
LLM_RETRIES = Counter("fssai_llm_retries_total", "Retried provider attempts", ["agent", "step", "provider"])
LLM_TOKENS = Counter("fssai_llm_tokens_total", "Tokens used", ["agent", "model_alias", "kind"])
LLM_COST = Counter("fssai_llm_cost_usd_total", "Cost in USD at call time", ["agent", "step", "model_alias"])
BREAKER_STATE = Gauge("fssai_llm_breaker_state", "Circuit breaker state: 0 closed, 1 half-open, 2 open",
                      ["provider"])
BREAKER_OPENED = Counter("fssai_llm_breaker_opened_total", "Times the circuit breaker opened", ["provider"])
