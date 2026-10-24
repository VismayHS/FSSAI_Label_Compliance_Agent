"""Correlation ids, structured access logs and HTTP metrics for every request (D5, F8)."""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram

from fssai_contracts.schemas import utcnow

log = logging.getLogger("fssai.api")

CORRELATION_HEADER = "X-Correlation-Id"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")  # anything else is replaced, so ids can't inject into logs

HTTP_REQUESTS = Counter("fssai_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_SECONDS = Histogram("fssai_http_request_duration_seconds", "HTTP request latency", ["method", "route"],
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))


def event(name: str, **fields) -> None:
    log.info(json.dumps({"event": name, "ts": utcnow().isoformat(), **fields}, default=str))


def correlation_id_from(request: Request) -> str:
    supplied = request.headers.get(CORRELATION_HEADER, "")
    return supplied if _SAFE_ID.match(supplied) else uuid.uuid4().hex


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlate(request: Request, call_next):
        request.state.correlation_id = correlation_id_from(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - t0
        route = getattr(request.scope.get("route"), "path", "unmatched")  # the template, not the raw path
        response.headers[CORRELATION_HEADER] = request.state.correlation_id
        HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        HTTP_SECONDS.labels(request.method, route).observe(elapsed)
        if route not in ("/metrics", "/healthz"):
            event("http_request", correlation_id=request.state.correlation_id, method=request.method,
                  route=route, status=response.status_code, latency_ms=round(elapsed * 1000, 1))
        return response
