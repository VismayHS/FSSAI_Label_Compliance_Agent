"""PostgresQuarantine against a real Postgres. Skipped unless FSSAI_TEST_DATABASE_URL points at a database these
tests may wipe, e.g. a throwaway container:

    docker run -d --rm --name fssai-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
    FSSAI_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres pytest packages/gate -q
"""
import os
from pathlib import Path

import pytest

from fssai_gate.gate import RequestGate, quarantine_from_env

from gate_helpers import with_

URL = os.environ.get("FSSAI_TEST_DATABASE_URL", "")
SCHEMA = Path(__file__).resolve().parents[3] / "infra" / "postgres" / "init" / "20-vihaan-quarantine.sql"
pytestmark = pytest.mark.skipif(not URL, reason="set FSSAI_TEST_DATABASE_URL to a disposable Postgres")


@pytest.fixture
def store(monkeypatch):
    import psycopg
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("TRUNCATE quarantine")
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("QUARANTINE_STORE", "auto")
    s = quarantine_from_env()
    assert type(s).__name__ == "PostgresQuarantine"
    yield s
    s.close()


def test_reject_is_written_and_read_back(store):
    gate = RequestGate(quarantine=store)
    raw = with_("nutrition.added_sugars_g", 50)
    d = gate.check(raw, "client-pg")
    rec = store.get(d.quarantine_id)
    assert rec.client_id == "client-pg" and rec.payload == raw and rec.errors[0].code == "XF-04"
    assert [r.quarantine_id for r in store.recent(5)] == [d.quarantine_id]


def test_database_down_keeps_rejects_in_memory_and_reads_still_work(store):
    store.pool.close()
    d = RequestGate(quarantine=store).check({"bad": True}, "c")
    assert store.fallback.get(d.quarantine_id) is not None
    assert [r.quarantine_id for r in store.recent(5)] == [d.quarantine_id], "reads degrade, they do not raise"
    assert store.get(d.quarantine_id) is not None
