"""The stub provider: POST /v1/chat/completions answers like an OpenAI-compatible endpoint.

Reply: picked by the system prompt's tag "[prompt:<name>@<version>]" (LLM_Context §6.5) from
fixtures/<name>@<version>.json, then fixtures/<name>.json, then fixtures/_default.json. A fixture is
{"content": "<text>"} or any other JSON object, which is sent back serialised (for json_mode prompts).
Fixture files are copies of what the real prompts should return; see fixtures/README.md.

Delay: log-normal with STUB_LATENCY_MEAN_S and STUB_LATENCY_P95_S (latency.py). Usage: token counts
estimated at ~4 characters per token, so cost tracking downstream sees realistic numbers.

Faults (circuit-breaker demo, A5): STUB_DOWN=1 answers 503, STUB_DOWN=hang never answers in time,
STUB_FAIL_RATE=0.2 fails 20% of calls with 500, STUB_RATE_LIMIT_RATE=0.1 answers 429 with Retry-After.
All four can be changed at runtime, without a restart:
    curl -X POST localhost:8080/admin/faults -H 'content-type: application/json' -d '{"down": "1"}'
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from .latency import LogNormal

log = logging.getLogger("fssai.stub_llm")
TAG = re.compile(r"\[prompt:([^@\]\s]+)@([^\]\s]+)\]")
FIXTURES = Path(__file__).parent / "fixtures"

REQUESTS = Counter("fssai_stub_requests_total", "Stub LLM requests", ["prompt", "outcome"])
LATENCY = Histogram("fssai_stub_latency_seconds", "Stub LLM response delay", ["prompt"],
                    buckets=(0.1, 0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 20, 30))
FAULTS = Gauge("fssai_stub_fault", "Active stub faults (1 = on, or the configured rate)", ["fault"])


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip() or default


@dataclass(frozen=True)
class Settings:
    latency_mean_s: float = 1.5
    latency_p95_s: float = 4.0
    fail_rate: float = 0.0
    rate_limit_rate: float = 0.0
    down: str = "0"                  # 0 | 1 (503) | hang
    hang_s: float = 300.0
    fixtures_dir: Path = FIXTURES
    seed: int | None = None

    @classmethod
    def from_env(cls) -> Settings:
        seed = _env("STUB_SEED", "")
        return cls(latency_mean_s=float(_env("STUB_LATENCY_MEAN_S", "1.5")),
                   latency_p95_s=float(_env("STUB_LATENCY_P95_S", "4")),
                   fail_rate=float(_env("STUB_FAIL_RATE", "0")),
                   rate_limit_rate=float(_env("STUB_RATE_LIMIT_RATE", "0")),
                   down=_env("STUB_DOWN", "0").lower(),
                   fixtures_dir=Path(_env("STUB_FIXTURES_DIR", str(FIXTURES))),
                   seed=int(seed) if seed else None)


@dataclass
class State:
    settings: Settings
    rng: random.Random
    latency: LogNormal | None = None
    fixtures: dict[str, object] = field(default_factory=dict)

    def apply(self, settings: Settings) -> None:
        self.settings = settings
        self.latency = LogNormal.from_mean_p95(settings.latency_mean_s, settings.latency_p95_s)
        FAULTS.labels("down").set(0 if settings.down in ("0", "false", "") else 1)
        FAULTS.labels("fail_rate").set(settings.fail_rate)
        FAULTS.labels("rate_limit_rate").set(settings.rate_limit_rate)


class FaultUpdate(BaseModel):
    down: str | None = None
    fail_rate: float | None = None
    rate_limit_rate: float | None = None
    latency_mean_s: float | None = None
    latency_p95_s: float | None = None


def _tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4)) if text else 0


def _fixture(state: State, name: str | None, version: str | None) -> object:
    candidates = ([f"{name}@{version}", name] if name else []) + ["_default"]
    for key in candidates:
        if key not in state.fixtures:
            path = state.settings.fixtures_dir / f"{key}.json"
            state.fixtures[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if state.fixtures[key] is not None:
            return state.fixtures[key]
    return {"content": "stub response"}


def _content(fixture: object, json_mode: bool, prompt: str | None) -> str:
    if isinstance(fixture, dict) and isinstance(fixture.get("content"), str) and len(fixture) == 1:
        text = fixture["content"]
        return json.dumps({"answer": text, "stub": True, "prompt": prompt}) if json_mode and not text.startswith("{") else text
    return json.dumps(fixture)


def create_app(settings: Settings | None = None, *, rng: random.Random | None = None, sleep=asyncio.sleep) -> FastAPI:
    settings = settings or Settings.from_env()
    state = State(settings=settings, rng=rng or random.Random(settings.seed))
    state.apply(settings)
    app = FastAPI(title="FSSAI stub LLM", version="0.1.0",
                  description="OpenAI-compatible stand-in for the LLM provider, for load tests and fault demos.")
    app.state.stub = state

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Response:
        body = await request.json()
        messages = body.get("messages") or []
        text_in = "\n".join(str(m.get("content", "")) for m in messages)
        system = next((str(m.get("content", "")) for m in messages if m.get("role") == "system"), text_in)
        m = TAG.search(system) or TAG.search(text_in)
        name, version = (m.group(1), m.group(2)) if m else (None, None)
        label = name or "untagged"
        s = state.settings
        t0 = time.perf_counter()

        if s.down == "hang":
            await sleep(s.hang_s)
        if s.down in ("1", "true", "yes", "hang"):
            REQUESTS.labels(label, "down").inc()
            return JSONResponse({"error": {"message": "stub provider is down (STUB_DOWN)", "type": "unavailable"}},
                                status_code=503)
        delay = state.latency.sample(state.rng) if state.latency else 0.0
        if delay:
            await sleep(delay)
        LATENCY.labels(label).observe(time.perf_counter() - t0)
        roll = state.rng.random()
        if roll < s.rate_limit_rate:
            REQUESTS.labels(label, "rate_limited").inc()
            return JSONResponse({"error": {"message": "rate limited (STUB_RATE_LIMIT_RATE)", "type": "rate_limit"}},
                                status_code=429, headers={"Retry-After": "1"})
        if roll < s.rate_limit_rate + s.fail_rate:
            REQUESTS.labels(label, "error").inc()
            return JSONResponse({"error": {"message": "injected failure (STUB_FAIL_RATE)", "type": "server_error"}},
                                status_code=500)

        json_mode = (body.get("response_format") or {}).get("type") == "json_object"
        content = _content(_fixture(state, name, version), json_mode, name)
        REQUESTS.labels(label, "ok").inc()
        usage = {"prompt_tokens": _tokens(text_in), "completion_tokens": _tokens(content)}
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        return JSONResponse({
            "id": f"chatcmpl-stub-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "created": int(time.time()),
            "model": body.get("model") or "stub",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": usage,
        })

    @app.get("/v1/models")
    def models() -> dict:
        return {"object": "list", "data": [{"id": "stub", "object": "model", "owned_by": "fssai-stub"}]}

    @app.get("/admin/faults")
    def get_faults() -> dict:
        s = state.settings
        return {"down": s.down, "fail_rate": s.fail_rate, "rate_limit_rate": s.rate_limit_rate,
                "latency_mean_s": s.latency_mean_s, "latency_p95_s": s.latency_p95_s}

    @app.post("/admin/faults")
    def set_faults(update: FaultUpdate) -> dict:
        changes = {k: v for k, v in update.model_dump().items() if v is not None}
        if "down" in changes:
            changes["down"] = str(changes["down"]).lower()
        state.apply(replace(state.settings, **changes))
        log.warning("stub faults changed: %s", changes)
        return get_faults()

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict:
        # ready even while "down": the fault is the stub's job, and the healthcheck must not restart it
        return {"ready": True, "down": state.settings.down}

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    try:  # JSON logs when the shared library is installed (it is in the image)
        from fssai_observability import setup_logging

        setup_logging("stub-llm")
    except ImportError:
        logging.basicConfig(level=_env("LOG_LEVEL", "INFO"))
    return app
