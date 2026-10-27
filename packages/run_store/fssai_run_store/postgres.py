"""PostgresRunStore: runs and their step traces in Postgres (the RunStore seam; D5, A7).

Every API replica and worker shares it, which queue mode needs (/readyz refuses the in-memory store
there). Schema: infra/postgres/init/10-vismay-runs.sql. `runs.doc` holds the full RunStatus; once a run
has a result, `run_steps` gets one row per step, so cost per step and run reconstruction work in plain SQL.

Switch on: IMPL_RUN_STORE=fssai_run_store.postgres:PostgresRunStore  (reads DATABASE_URL)
"""
from __future__ import annotations

import os

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from fssai_contracts.schemas import RunStatus

# An older status never overwrites a newer one, so a late or retried save can't move a run backwards.
_UPSERT = """
INSERT INTO runs (run_id, state, submitted_at, updated_at, client_id, correlation_id,
                  product_name, route, complete, cost_usd, doc)
VALUES (%(run_id)s, %(state)s, %(submitted_at)s, %(updated_at)s, %(client_id)s, %(correlation_id)s,
        %(product_name)s, %(route)s, %(complete)s, %(cost_usd)s, %(doc)s)
ON CONFLICT (run_id) DO UPDATE SET
    state = EXCLUDED.state, updated_at = EXCLUDED.updated_at, client_id = EXCLUDED.client_id,
    correlation_id = EXCLUDED.correlation_id, product_name = EXCLUDED.product_name, route = EXCLUDED.route,
    complete = EXCLUDED.complete, cost_usd = EXCLUDED.cost_usd, doc = EXCLUDED.doc
WHERE runs.updated_at <= EXCLUDED.updated_at
"""
_STEP = """
INSERT INTO run_steps (run_id, step_index, agent, kind, name, started_at, latency_ms, prompt_name,
                       prompt_version, prompt_tokens, completion_tokens, cost_usd, error, input, output)
VALUES (%(run_id)s, %(step_index)s, %(agent)s, %(kind)s, %(name)s, %(started_at)s, %(latency_ms)s,
        %(prompt_name)s, %(prompt_version)s, %(prompt_tokens)s, %(completion_tokens)s, %(cost_usd)s,
        %(error)s, %(input)s, %(output)s)
"""


def _step_row(run_id: str, step: dict) -> dict:
    return {**step, "run_id": run_id, "input": Jsonb(step["input"]), "output": Jsonb(step["output"])}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip() or default


class PostgresRunStore:
    def __init__(self, database_url: str, *, max_connections: int = 5, timeout_s: float = 5.0) -> None:
        # open=True connects in the background: the service starts even if Postgres is a moment late,
        # and a query waits at most timeout_s before failing (so /readyz reports it instead of hanging).
        self.pool = ConnectionPool(database_url, min_size=1, max_size=max_connections, timeout=timeout_s,
                                   kwargs={"connect_timeout": int(timeout_s)},
                                   check=ConnectionPool.check_connection, open=True)

    @classmethod
    def from_registry(cls) -> PostgresRunStore:
        url = _env("DATABASE_URL")
        if not url:
            raise RuntimeError("IMPL_RUN_STORE is the Postgres store but DATABASE_URL is not set")
        return cls(url, max_connections=int(_env("RUN_STORE_MAX_CONNECTIONS", "5")))

    def save(self, status: RunStatus) -> None:
        result = status.result
        row = {
            "run_id": status.run_id, "state": status.state.value, "submitted_at": status.submitted_at,
            "updated_at": status.updated_at, "client_id": status.client_id, "correlation_id": status.correlation_id,
            "product_name": status.request.label.product_name if status.request else None,
            "route": result.routing.route.value if result else None,
            "complete": result.complete if result else None,
            "cost_usd": result.totals.cost_usd if result else None,
            "doc": Jsonb(status.model_dump(mode="json")),
        }
        with self.pool.connection() as conn, conn.transaction():
            written = conn.execute(_UPSERT, row).rowcount
            if written and result is not None:
                conn.execute("DELETE FROM run_steps WHERE run_id = %s", (status.run_id,))
                with conn.cursor() as cur:
                    cur.executemany(_STEP, [_step_row(status.run_id, s.model_dump(mode="json")) for s in result.steps])

    def get(self, run_id: str) -> RunStatus | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT doc FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        return RunStatus.model_validate(row[0]) if row else None

    def recent(self, limit: int = 50) -> list[RunStatus]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT doc FROM runs ORDER BY updated_at DESC LIMIT %s", (limit,)).fetchall()
        return [RunStatus.model_validate(r[0]) for r in rows]

    def close(self) -> None:
        self.pool.close()
