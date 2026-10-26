"""RequestGate: the single ingestion boundary (contexts/Vihaan.md V1.2; F2, D1, D7).

Order: per-client rate limit -> schema/type -> version, ranges, lengths, formats -> category -> cross-field rules
(fssai_gate.rules; the published contract is docs/data-contract.md) -> quarantine every reject with its errors.
Rules (interface: fssai_contracts.interfaces.RequestGate; checked by conformance.check_gate):
- never raises on bad input: a reject is GateDecision(accepted=False, errors=[FieldError...], quarantine_id=...);
- all field errors are collected, not just the first;
- a rate-limited call is GateDecision(accepted=False, rate_limited=True, retry_after_s=...) and is *not*
  quarantined: it was not malformed, and the limit is checked before any validation work is spent on it;
- only an accepted decision carries `request`; the API enqueues nothing on a reject (demo #4).

Env: RATE_LIMIT_PER_MIN, RATE_LIMIT_BURST, RATE_LIMIT_BACKEND (auto | redis | memory), REDIS_URL,
     QUARANTINE_STORE (auto | postgres | memory), DATABASE_URL, CORPUS_CATEGORIES.
Switch on: IMPL_GATE=fssai_gate.gate:RequestGate
"""
from __future__ import annotations

import json
import logging
import os

from prometheus_client import Counter

from fssai_contracts.schemas import FieldError, GateDecision

from .quarantine import InMemoryQuarantine, PostgresQuarantine, QuarantineRecord, QuarantineStore
from .ratelimit import MemoryTokenBucket, NoLimit, RateLimiter, RedisTokenBucket
from .rules import validate

log = logging.getLogger("fssai.gate")

GATE_DECISIONS = Counter("fssai_gate_decisions_total", "Gate decisions by outcome", ["outcome"])
GATE_ERRORS = Counter("fssai_gate_field_errors_total", "Field errors found at the gate, by code", ["code"])


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip() or default


def _event(name: str, **fields) -> None:
    log.info(json.dumps({"event": name, **fields}, default=str))


def limiter_from_env() -> RateLimiter:
    per_min = float(_env("RATE_LIMIT_PER_MIN", "30"))
    burst = int(_env("RATE_LIMIT_BURST", "10"))
    if per_min <= 0:
        return NoLimit()
    backend, url = _env("RATE_LIMIT_BACKEND", "auto").lower(), _env("REDIS_URL")
    if backend == "memory" or (backend == "auto" and not url):
        return MemoryTokenBucket(per_min, burst)
    import redis

    client = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
    if backend == "auto":
        try:
            client.ping()
        except Exception as exc:  # noqa: BLE001 - e.g. a local run where the Compose host "redis" does not exist
            _event("gate_rate_limit_backend", backend="memory", reason=f"{type(exc).__name__}: redis unreachable")
            return MemoryTokenBucket(per_min, burst)
    _event("gate_rate_limit_backend", backend="redis")
    return RedisTokenBucket(client, per_min, burst)


def quarantine_from_env() -> QuarantineStore:
    backend, url = _env("QUARANTINE_STORE", "auto").lower(), _env("DATABASE_URL")
    if backend == "memory" or (backend == "auto" and not url):
        return InMemoryQuarantine()
    if backend == "auto":
        try:
            import psycopg

            with psycopg.connect(url, connect_timeout=2) as conn:
                conn.execute("SELECT 1 FROM quarantine LIMIT 1")
        except Exception as exc:  # noqa: BLE001 - no database (or no table) here: keep rejects in memory
            _event("gate_quarantine_backend", backend="memory", reason=type(exc).__name__)
            return InMemoryQuarantine()
    _event("gate_quarantine_backend", backend="postgres")
    return PostgresQuarantine(url)


class RequestGate:
    def __init__(self, limiter: RateLimiter | None = None, quarantine: QuarantineStore | None = None) -> None:
        self.limiter = NoLimit() if limiter is None else limiter
        self.quarantine = InMemoryQuarantine() if quarantine is None else quarantine  # an empty store is falsy

    @classmethod
    def from_registry(cls) -> RequestGate:
        return cls(limiter=limiter_from_env(), quarantine=quarantine_from_env())

    def check(self, raw: dict, client_id: str) -> GateDecision:
        allowed, retry_after = self.limiter.take(client_id)
        if not allowed:
            GATE_DECISIONS.labels("rate_limited").inc()
            return GateDecision(accepted=False, rate_limited=True, retry_after_s=max(retry_after, 0.1))
        try:
            request, errors = validate(raw)
        except Exception as exc:  # noqa: BLE001 - the boundary never raises; a bug here is a reject, not a 500
            log.exception("gate validation crashed")
            request, errors = None, [FieldError(loc="body", message=f"Could not validate the request "
                                                f"({type(exc).__name__}).", code="internal")]
        if request is not None:
            GATE_DECISIONS.labels("accepted").inc()
            return GateDecision(accepted=True, request=request)

        for e in errors:
            GATE_ERRORS.labels(e.code).inc()
        record = QuarantineRecord(client_id=client_id, errors=errors, payload=raw,
                                  schema_version=raw.get("schema_version") if isinstance(raw, dict) and
                                  isinstance(raw.get("schema_version"), str) else None)
        qid = self.quarantine.put(record)
        GATE_DECISIONS.labels("rejected").inc()
        _event("gate_rejected", quarantine_id=qid, client_id=client_id, error_count=len(errors),
               codes=sorted({e.code for e in errors}))
        return GateDecision(accepted=False, errors=errors, quarantine_id=qid)
