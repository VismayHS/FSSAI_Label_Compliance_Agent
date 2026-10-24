"""RequestGate: the single ingestion boundary (contexts/Vihaan.md V1.2). Day-0 skeleton.

Order: per-client rate limit (RATE_LIMIT_PER_MIN, RATE_LIMIT_BURST; Redis so every API replica shares it)
-> schema, range, category and cross-field validation -> quarantine every reject with its field errors.
Rules (interface: fssai_contracts.interfaces.RequestGate; checked by conformance.check_gate):
- never raises on bad input: a reject is GateDecision(accepted=False, errors=[FieldError...], quarantine_id=...);
- a rate-limited call is GateDecision(accepted=False, rate_limited=True, retry_after_s=...), not quarantined;
- the API enqueues nothing on a reject (demo #4); the quarantine router (V3.5) reads what you stored.

Switch on: IMPL_GATE=fssai_gate.gate:RequestGate
"""
from __future__ import annotations

from fssai_contracts.schemas import GateDecision


class RequestGate:
    def check(self, raw: dict, client_id: str) -> GateDecision:
        raise NotImplementedError("V1.2: rate limit, validate, quarantine")
