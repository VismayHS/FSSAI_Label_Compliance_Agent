"""GatewayLLMClient: the production LLMClient (A5, L5).

Per logical call:
1. Try the primary provider through its circuit breaker. Every attempt has a timeout capped by the
   run's remaining wall-clock budget. Retryable failures (timeouts, connection errors, 429, 5xx,
   malformed replies) are retried with exponential backoff and full jitter, honouring Retry-After,
   up to LLM_MAX_RETRIES extra attempts and never past the run deadline.
2. If the primary is unavailable and LLM_FALLBACK_* is configured, try the fallback the same way
   and mark the response `degraded`.
3. Otherwise raise ProviderUnavailable; the pipeline turns that into complete=False and
   regulatory-review with an honest reason.

Exactly one "llm" step is recorded per logical call, with tokens, cost at call time, prompt
name and version, attempts and the provider alias. Provider URLs, keys and model ids come only
from the environment (D4); traces carry the alias ("primary" / "fallback"), never the model id.
"""
from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping

import httpx

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import LLMMessage, LLMResponse, PromptTemplate

from .breaker import BreakerStore, CircuitBreaker, MemoryBreakerStore, RedisBreakerStore, State
from .metrics import LLM_CALLS, LLM_COST, LLM_RETRIES, LLM_TOKENS

USER_AGENT = "fssai-label-agent/0.1"


@dataclass(frozen=True)
class Provider:
    alias: str
    base_url: str
    api_key: str
    model: str
    price_prompt_per_1k: float = 0.0
    price_completion_per_1k: float = 0.0

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return round(prompt_tokens * self.price_prompt_per_1k / 1000
                     + completion_tokens * self.price_completion_per_1k / 1000, 8)


class _Retryable(Exception):
    def __init__(self, reason: str, retry_after_s: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after_s = retry_after_s


def _num(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").split("#", 1)[0].strip()
    return float(raw) if raw else default


def _error_code(response: httpx.Response) -> str:
    """`type/code` from an OpenAI-style error body, or "". Only these two fields: the provider's message can echo the
    prompt (label text) or name the model id, and neither may reach a trace (D4)."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        return ""
    safe = [re.sub(r"[^A-Za-z0-9_.-]", "", str(error.get(k) or ""))[:40] for k in ("type", "code")]
    return "/".join(safe) if any(safe) else ""


_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_UNIT_S = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}

# A model output problem the provider reports as a 400: retried like a malformed reply, not treated as an outage.
_RETRYABLE_400 = ("/json_validate_failed", "/tool_use_failed")


def _duration_s(text: str) -> float | None:
    """'4.11s', '592ms', '1m2.5s' -> seconds (the format of the x-ratelimit-reset-* headers)."""
    parts = _DURATION.findall(text.strip())
    return sum(float(n) * _UNIT_S[u] for n, u in parts) if parts else None


def _retry_after(response: httpx.Response) -> float | None:
    """How long the provider says to wait: Retry-After, else (on a 429) the time until its token budget refills."""
    try:
        return max(0.0, float(response.headers["retry-after"]))
    except (KeyError, ValueError):
        pass  # absent, or an HTTP date we don't bother parsing
    if response.status_code == 429 and "x-ratelimit-reset-tokens" in response.headers:
        return _duration_s(response.headers["x-ratelimit-reset-tokens"])
    return None


class GatewayLLMClient:
    def __init__(self, primary: Provider, fallback: Provider | None = None, *,
                 timeout_s: float = 30.0, max_retries: int = 3,
                 breaker_store: BreakerStore | None = None, breaker_threshold: int = 5,
                 breaker_cooldown_s: float = 30.0, http: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep, jitter: Callable[[], float] = random.random,
                 backoff_base_s: float = 0.5, backoff_cap_s: float = 8.0,
                 clock: Callable[[], float] = time.time) -> None:
        store = breaker_store or MemoryBreakerStore()
        self.providers = [p for p in (primary, fallback) if p]
        self.breakers = {p.alias: CircuitBreaker(p.alias, store, threshold=breaker_threshold,
                                                 cooldown_s=breaker_cooldown_s, clock=clock)
                         for p in self.providers}
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self.http = http or httpx.Client()
        self.sleep, self.jitter = sleep, jitter
        self.backoff_base_s, self.backoff_cap_s = backoff_base_s, backoff_cap_s

    @classmethod
    def from_registry(cls) -> GatewayLLMClient:
        return cls.from_env(os.environ)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> GatewayLLMClient:
        def provider(alias: str, prefix: str, price_prefix: str) -> Provider:
            return Provider(alias=alias, base_url=env[f"{prefix}_BASE_URL"].strip().rstrip("/"),
                            api_key=env.get(f"{prefix}_API_KEY", "").strip(), model=env[f"{prefix}_MODEL"].strip(),
                            price_prompt_per_1k=_num(env, f"{price_prefix}_PRICE_PROMPT_PER_1K", 0.0),
                            price_completion_per_1k=_num(env, f"{price_prefix}_PRICE_COMPLETION_PER_1K", 0.0))

        missing = [n for n in ("LLM_BASE_URL", "LLM_MODEL") if not env.get(n, "").strip()]
        if missing:
            raise RuntimeError(f"GatewayLLMClient needs {', '.join(missing)} in the environment (.env)")
        fallback = None
        if env.get("LLM_FALLBACK_BASE_URL", "").strip() and env.get("LLM_FALLBACK_MODEL", "").strip():
            fallback = provider("fallback", "LLM_FALLBACK", "LLM_FALLBACK")
        store_kind = env.get("BREAKER_STORE", "memory").split("#", 1)[0].strip() or "memory"
        if store_kind == "redis":
            store: BreakerStore = RedisBreakerStore.from_url(env["REDIS_URL"])
        elif store_kind == "memory":
            store = MemoryBreakerStore()
        else:
            raise RuntimeError(f"BREAKER_STORE must be 'memory' or 'redis', not '{store_kind}'")
        return cls(provider("primary", "LLM", "LLM"), fallback,
                   timeout_s=_num(env, "LLM_TIMEOUT_S", 30.0), max_retries=int(_num(env, "LLM_MAX_RETRIES", 3)),
                   breaker_store=store, breaker_threshold=int(_num(env, "BREAKER_FAILURE_THRESHOLD", 5)),
                   breaker_cooldown_s=_num(env, "BREAKER_COOLDOWN_S", 30.0))

    # ------------------------------------------------------------------ LLMClient

    def complete(self, messages: list[LLMMessage], ctx: RunContext, *, agent: str, step: str,
                 prompt: PromptTemplate | None = None, json_mode: bool = False) -> LLMResponse:
        ctx.check_budget()
        t0 = time.monotonic()
        failures: list[str] = []
        attempts = 0
        for provider in self.providers:
            try:
                data, used = self._call(provider, messages, json_mode, ctx, agent, step)
            except BudgetExceeded:
                self._record(ctx, agent, step, prompt, messages, t0, attempts, error="run deadline reached")
                raise
            except ProviderUnavailable as exc:
                attempts += getattr(exc, "attempts", 0)
                failures.append(f"{provider.alias}: {exc}")
                continue
            attempts += used
            usage = data.get("usage") or {}
            pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
            resp = LLMResponse(text=data["choices"][0]["message"].get("content") or "",
                               model_alias=provider.alias, prompt_tokens=pt, completion_tokens=ct,
                               cost_usd=provider.cost(pt, ct), latency_ms=(time.monotonic() - t0) * 1000,
                               degraded=provider is not self.providers[0])
            self._record(ctx, agent, step, prompt, messages, t0, attempts, resp=resp)
            LLM_CALLS.labels(agent, step, provider.alias, "degraded" if resp.degraded else "ok").inc()
            LLM_TOKENS.labels(agent, provider.alias, "prompt").inc(pt)
            LLM_TOKENS.labels(agent, provider.alias, "completion").inc(ct)
            LLM_COST.labels(agent, step, provider.alias).inc(resp.cost_usd)
            return resp

        reason = "; ".join(failures)
        self._record(ctx, agent, step, prompt, messages, t0, attempts, error=reason)
        LLM_CALLS.labels(agent, step, "none", "unavailable").inc()
        raise ProviderUnavailable(reason)

    # ------------------------------------------------------------------ internals

    def _call(self, provider: Provider, messages: list[LLMMessage], json_mode: bool, ctx: RunContext,
              agent: str, step: str) -> tuple[dict, int]:
        breaker = self.breakers[provider.alias]
        state: State = breaker.before_call()  # BreakerOpen fails fast, before any HTTP call
        body: dict = {"model": provider.model, "messages": [m.model_dump() for m in messages], "temperature": 0}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        # Our own User-Agent: Cloudflare-fronted providers (Groq) refuse library defaults with 403 (error 1010)
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        last = "no attempt made"
        attempt = 0
        for attempt in range(1, self.max_retries + 2):
            remaining = ctx.remaining_s()
            if remaining <= 0:
                raise BudgetExceeded(f"wall-clock limit {ctx.limits.max_wall_s}s reached")
            try:
                data = self._attempt(provider, body, headers, min(self.timeout_s, remaining))
                breaker.on_success()
                return data, attempt
            except _Retryable as exc:
                last = str(exc)
                if attempt > self.max_retries:
                    break
                delay = self.jitter() * min(self.backoff_cap_s, self.backoff_base_s * 2 ** (attempt - 1))
                if exc.retry_after_s is not None:
                    delay = max(delay, exc.retry_after_s)
                if delay >= ctx.remaining_s():
                    break  # waiting would cross the run deadline
                LLM_RETRIES.labels(agent, step, provider.alias).inc()
                ctx.event("llm_retry", agent=agent, step=step, provider=provider.alias,
                          attempt=attempt, reason=last, delay_s=round(delay, 3))
                self.sleep(delay)
            except ProviderUnavailable as exc:  # non-retryable answer, e.g. 401 or 400
                last = str(exc)
                break
        breaker.on_failure(state)
        error = ProviderUnavailable(f"{last} after {attempt} attempt(s)")
        error.attempts = attempt  # type: ignore[attr-defined]
        raise error

    def _attempt(self, provider: Provider, body: dict, headers: dict, timeout_s: float) -> dict:
        try:
            r = self.http.post(f"{provider.base_url}/chat/completions", json=body, headers=headers,
                               timeout=httpx.Timeout(timeout_s))
        except httpx.TimeoutException as exc:
            raise _Retryable(f"timeout after {timeout_s:.1f}s") from exc
        except httpx.TransportError as exc:
            raise _Retryable(f"connection error: {type(exc).__name__}") from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise _Retryable(f"HTTP {r.status_code}", _retry_after(r))
        if r.status_code != 200:
            code = _error_code(r)
            if code.endswith(_RETRYABLE_400):  # the model's own output was unusable: same as a malformed reply
                raise _Retryable(f"HTTP {r.status_code} {code}")
            raise ProviderUnavailable(f"HTTP {r.status_code} {code} (not retried)".replace("  ", " "))
        try:
            data = r.json()
            data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise _Retryable("malformed provider reply") from exc
        return data

    @staticmethod
    def _record(ctx: RunContext, agent: str, step: str, prompt: PromptTemplate | None,
                messages: list[LLMMessage], t0: float, attempts: int, *,
                resp: LLMResponse | None = None, error: str | None = None) -> None:
        output = {"attempts": attempts}
        if resp:
            output.update(text=resp.text, model_alias=resp.model_alias, degraded=resp.degraded)
        ctx.record(agent=agent, kind="llm", name=step, latency_ms=(time.monotonic() - t0) * 1000,
                   input={"messages": [m.model_dump() for m in messages]}, output=output,
                   prompt_name=prompt.name if prompt else None,
                   prompt_version=prompt.version if prompt else None,
                   prompt_tokens=resp.prompt_tokens if resp else 0,
                   completion_tokens=resp.completion_tokens if resp else 0,
                   cost_usd=resp.cost_usd if resp else 0.0, error=error)

