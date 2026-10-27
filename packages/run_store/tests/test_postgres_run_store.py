"""PostgresRunStore against a real Postgres. Skipped unless FSSAI_TEST_DATABASE_URL points at a database
these tests may wipe, e.g. a throwaway container:

    docker run -d --rm --name fssai-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
    FSSAI_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres pytest packages/run_store -q
"""
import os
from datetime import timedelta
from pathlib import Path

import pytest

from fssai_contracts.conformance import check_run_store, sample_request
from fssai_contracts.context import RunContext
from fssai_contracts.pipeline import ReferencePipeline
from fssai_contracts.schemas import RunState, RunStatus, utcnow

URL = os.environ.get("FSSAI_TEST_DATABASE_URL", "")
SCHEMA = Path(__file__).resolve().parents[3] / "infra" / "postgres" / "init" / "10-vismay-runs.sql"
pytestmark = pytest.mark.skipif(not URL, reason="set FSSAI_TEST_DATABASE_URL to a disposable Postgres")


@pytest.fixture
def store():
    from fssai_run_store.postgres import PostgresRunStore
    s = PostgresRunStore(URL)
    with s.pool.connection() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("TRUNCATE runs CASCADE")
    yield s
    s.close()


def finished_run() -> RunStatus:
    ctx = RunContext.new()
    request = sample_request(protein_g=8)
    result = ReferencePipeline.from_registry().run(request, ctx)
    now = utcnow()
    return RunStatus(run_id=ctx.run_id, state=RunState.COMPLETED, submitted_at=now, updated_at=now,
                     client_id="c1", correlation_id=ctx.correlation_id, request=request, result=result)


def test_conforms(store):
    check_run_store(store)


def test_round_trips_the_full_status(store):
    status = finished_run()
    store.save(status)
    assert store.get(status.run_id) == status


def test_writes_one_row_per_step_for_sql_reconstruction(store):
    status = finished_run()
    store.save(status)
    with store.pool.connection() as conn:
        rows = conn.execute("SELECT step_index, agent, kind, name, output FROM run_steps WHERE run_id = %s "
                            "ORDER BY step_index", (status.run_id,)).fetchall()
        route = conn.execute("SELECT route, complete FROM runs WHERE run_id = %s", (status.run_id,)).fetchone()
    assert [r[0] for r in rows] == [s.step_index for s in status.result.steps]
    tool = next(r for r in rows if r[2] == "tool")
    assert tool[4]["passages"], "tool steps keep their full passages (D5)"
    assert route == (status.result.routing.route.value, True)


def test_an_older_save_never_moves_a_run_backwards(store):
    status = finished_run()
    store.save(status)
    stale = status.model_copy(update={"state": RunState.RUNNING, "result": None,
                                      "updated_at": status.updated_at - timedelta(seconds=5)})
    store.save(stale)
    assert store.get(status.run_id).state == RunState.COMPLETED
