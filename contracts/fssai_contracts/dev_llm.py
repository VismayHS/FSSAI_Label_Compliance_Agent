"""Minimal real LLM client for development, so agent work can start before the
production gateway (libs/llm_gateway, Vismay) exists.

Talks to any OpenAI-compatible chat endpoint. No retries, no circuit breaker,
no pricing: those are the gateway's job (A5, L5). Use with:

    IMPL_LLM=fssai_contracts.dev_llm:DevLLMClient
    LLM_BASE_URL=...   LLM_API_KEY=...   LLM_MODEL=...   (in .env only, never in code)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .interfaces import ProviderUnavailable
from .schemas import LLMResponse


class DevLLMClient:
    def __init__(self) -> None:
        self.base_url = os.environ["LLM_BASE_URL"].rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ["LLM_MODEL"]
        self.timeout = float(os.environ.get("LLM_TIMEOUT_S", "30") or 30)

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        body = {"model": self.model, "messages": [m.model_dump() for m in messages], "temperature": 0}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, ctx.remaining_s() or self.timeout)) as r:
                data = json.load(r)
        except (urllib.error.URLError, TimeoutError) as exc:
            ctx.record(agent=agent, kind="llm", name=step, error=str(exc),
                       latency_ms=(time.monotonic() - t0) * 1000)
            raise ProviderUnavailable(str(exc)) from exc
        usage = data.get("usage") or {}
        resp = LLMResponse(
            text=data["choices"][0]["message"]["content"] or "", model_alias="dev",
            prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=(time.monotonic() - t0) * 1000,
        )
        ctx.record(agent=agent, kind="llm", name=step, latency_ms=resp.latency_ms,
                   prompt_name=prompt.name if prompt else None,
                   prompt_version=prompt.version if prompt else None,
                   prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens)
        return resp
