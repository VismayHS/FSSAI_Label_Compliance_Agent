"""RequestGate end to end: order, quarantine, rate limiting, never raising, building from env."""
import fakeredis
import pytest

from fssai_gate.gate import RequestGate, limiter_from_env, quarantine_from_env
from fssai_gate.quarantine import InMemoryQuarantine
from fssai_gate.ratelimit import MemoryTokenBucket, NoLimit, RedisTokenBucket

from gate_helpers import valid, with_


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_accepted_request_is_typed_and_not_quarantined():
    gate = RequestGate()
    d = gate.check(valid(), "client-a")
    assert d.accepted and d.request.nutrition.protein_g == 10 and d.quarantine_id is None and not d.errors
    assert len(gate.quarantine) == 0


def test_reject_is_quarantined_with_payload_client_errors_and_time():
    gate = RequestGate()
    raw = with_("nutrition.added_sugars_g", 50)
    d = gate.check(raw, "client-a")
    assert not d.accepted and d.request is None and d.quarantine_id
    rec = gate.quarantine.get(d.quarantine_id)
    assert rec.client_id == "client-a" and rec.payload == raw and rec.received_at and rec.schema_version == "1.0"
    assert [e.code for e in rec.errors] == [e.code for e in d.errors]


def test_recent_quarantine_is_newest_first():
    gate = RequestGate()
    ids = [gate.check({"n": i}, "c").quarantine_id for i in range(3)]
    assert [r.quarantine_id for r in gate.quarantine.recent(2)] == ids[::-1][:2]


def test_memory_quarantine_is_bounded():
    q = InMemoryQuarantine(max_records=2)
    gate = RequestGate(quarantine=q)
    for i in range(5):
        gate.check({"n": i}, "c")
    assert len(q) == 2


def test_rate_limit_trips_before_validation_and_is_not_quarantined():
    clock = Clock()
    gate = RequestGate(limiter=MemoryTokenBucket(per_min=60, burst=2, clock=clock))
    assert gate.check(valid(), "c").accepted and gate.check({"bad": 1}, "c").quarantine_id
    limited = gate.check({"also": "bad"}, "c")
    assert limited.rate_limited and not limited.accepted and limited.retry_after_s == pytest.approx(1.0)
    assert limited.quarantine_id is None and not limited.errors and len(gate.quarantine) == 1
    assert gate.check(valid(), "other-client").accepted, "buckets are per client"
    clock.t += 1.0
    assert gate.check(valid(), "c").accepted, "a token refills after 60/per_min seconds"


def test_redis_token_bucket_is_shared_by_replicas():
    server = fakeredis.FakeServer()
    a = RedisTokenBucket(fakeredis.FakeRedis(server=server), per_min=30, burst=3)
    b = RedisTokenBucket(fakeredis.FakeRedis(server=server), per_min=30, burst=3)
    results = [a.take("c")[0], b.take("c")[0], a.take("c")[0], b.take("c")]
    assert results[:3] == [True, True, True]
    allowed, retry = results[3]
    assert not allowed and 0 < retry <= 2.0  # 30/min -> one token every 2 s


def test_redis_down_fails_open():
    class Broken:
        def register_script(self, _):
            def run(**_):
                raise ConnectionError("redis down")
            return run
    bucket = RedisTokenBucket(Broken(), per_min=1, burst=1)
    assert bucket.take("c") == (True, 0.0) and bucket.failures == 1


def test_never_raises_on_hostile_input():
    gate = RequestGate()
    for raw in (None, [], "x", {"nutrition": {"other": {"a" * 500: "b"}}}, {"label": {"claims": [None, 3]}},
                {"package": "box"}, {"nutrition": {"protein_g": float("nan")}}):
        d = gate.check(raw, "c")
        assert not d.accepted and d.errors and d.quarantine_id


def test_internal_crash_is_a_reject_not_an_exception(monkeypatch):
    import fssai_gate.gate as g
    monkeypatch.setattr(g, "validate", lambda raw: 1 / 0)
    d = RequestGate().check(valid(), "c")
    assert not d.accepted and d.errors[0].code == "internal" and d.quarantine_id


def test_from_env_backends(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")
    assert isinstance(limiter_from_env(), NoLimit)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "30")
    assert isinstance(limiter_from_env(), MemoryTokenBucket)
    assert isinstance(quarantine_from_env(), InMemoryQuarantine)


def test_unreachable_redis_and_postgres_fall_back_to_memory(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://no-such-host.invalid:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@no-such-host.invalid:5432/db")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "auto")
    monkeypatch.setenv("QUARANTINE_STORE", "auto")
    assert isinstance(limiter_from_env(), MemoryTokenBucket)
    assert isinstance(quarantine_from_env(), InMemoryQuarantine)
