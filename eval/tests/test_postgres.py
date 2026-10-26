"""The Postgres paths of Vihaan's tables against a real database: feedback, live quality scores, feedback candidates,
and every SQL query in the quality dashboard. Skipped unless FSSAI_TEST_DATABASE_URL points at a database these
tests may wipe (CI provides one):

    docker run -d --rm --name fssai-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
    FSSAI_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres pytest eval -q
"""
import json
import os
import re
from pathlib import Path

import pytest

URL = os.environ.get("FSSAI_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="set FSSAI_TEST_DATABASE_URL to a disposable Postgres")
ROOT = Path(__file__).resolve().parents[2]
INIT = ROOT / "deploy" / "postgres" / "init"


@pytest.fixture
def db(monkeypatch):
    import psycopg
    pytest.importorskip("app.routers.feedback")
    PostgresRunStore = pytest.importorskip("fssai_run_store.postgres").PostgresRunStore

    with psycopg.connect(URL, autocommit=True) as conn:
        for sql in sorted(INIT.glob("*.sql")):  # the order Postgres applies them in Compose
            conn.execute(sql.read_text(encoding="utf-8"))
        conn.execute("TRUNCATE runs, quarantine CASCADE")
    monkeypatch.setenv("DATABASE_URL", URL)
    store = PostgresRunStore(URL)
    yield store
    store.close()


def finished(store, protein=12.0):
    from fssai_contracts.context import RunContext
    from fssai_contracts.conformance import sample_request
    from fssai_contracts.pipeline import ReferencePipeline
    from fssai_contracts.schemas import RunState, RunStatus, utcnow

    req, ctx = sample_request(protein_g=protein), RunContext.new()
    now = utcnow()
    store.save(RunStatus(run_id=ctx.run_id, state=RunState.COMPLETED, submitted_at=now, updated_at=now,
                         request=req, result=ReferencePipeline.from_registry().run(req, ctx)))
    return ctx.run_id


def test_feedback_store_round_trip(db, monkeypatch):
    from datetime import timedelta
    from app.routers.feedback import FeedbackRecord, PostgresFeedbackStore, store_from_env
    from fssai_contracts.schemas import utcnow

    monkeypatch.setenv("FEEDBACK_STORE", "auto")
    store = store_from_env()
    assert isinstance(store, PostgresFeedbackStore)
    run_id = finished(db)
    store.add(FeedbackRecord(run_id=run_id, satisfactory=False, reason="missed it", route="clear-for-print"))
    rows = store.since(utcnow() - timedelta(days=1))
    assert [(r.run_id, r.satisfactory, r.route) for r in rows] == [(run_id, False, "clear-for-print")]


def test_live_scores_are_written_once(db):
    from fssai_eval.judges import ReferenceJudge
    from fssai_eval.live import PostgresScores, score_once

    a, b = finished(db), finished(db, protein=8)
    sink = PostgresScores(URL)
    rows = score_once(db, sink, ReferenceJudge(), sample=10)
    assert {r["run_id"] for r in rows} == {a, b}
    assert score_once(db, sink, ReferenceJudge(), sample=10) == []
    n = sink.conn.execute("SELECT count(*), bool_and(citation_resolution = 1) FROM quality_scores").fetchone()
    assert n == (2, True)


def test_feedback_candidates_from_postgres(db):
    import psycopg
    from fssai_eval.loop import candidates, feedback_rows

    run_id = finished(db)
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("INSERT INTO feedback VALUES (%s, %s, false, 'wrong route', 'clear-for-print', 'c', now())",
                     ("f" * 32, run_id))
    new = candidates(feedback_rows(7, None), db, existing=set())
    assert [s.scenario_id for s in new] == [f"fb-{run_id[:12]}"]


def _plain_sql(sql: str) -> str:
    """Grafana's macros, replaced by what they expand to, so the queries run as plain SQL."""
    sql = re.sub(r"\$__timeFilter\((\w+)\)", r"\1 > now() - interval '7 days'", sql)
    return re.sub(r"\$__timeGroupAlias\((\w+), '[^']+'\)", r"date_trunc('hour', \1) AS time", sql)


def test_every_dashboard_query_runs(db):
    import psycopg

    finished(db)
    dash = json.loads((ROOT / "observability" / "grafana" / "dashboards" / "quality.json").read_text())
    queries = [t["rawSql"] for p in dash["panels"] for t in p.get("targets", []) if "rawSql" in t]
    assert len(queries) >= 10
    with psycopg.connect(URL, autocommit=True) as conn:
        for q in queries:
            conn.execute(_plain_sql(q)).fetchall()
