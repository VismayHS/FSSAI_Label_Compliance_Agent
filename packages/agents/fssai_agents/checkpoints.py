"""LangGraph checkpointing for the pipeline (docs/contexts/Namith.md, extras): a run interrupted mid-graph resumes.

PIPELINE_CHECKPOINTS picks the saver:
  (empty) | off   no checkpoints; a run interrupted mid-graph restarts from the beginning (the old behaviour)
  memory          in-process only (tests, inline development): survives a crashed node, not a dead process
  postgres        langgraph-checkpoint-postgres on PIPELINE_CHECKPOINT_URL, or DATABASE_URL (the run store's
                  database) when that is empty. This is what survives a worker that dies mid-run.

The thread id is the run id, so a re-queued job (RQ retries an abandoned job, apps/worker) finds its own checkpoint.

Deserialisation is restricted to the contract schemas. A checkpoint row is data written by our own workers, but
LangGraph's msgpack format can rebuild arbitrary classes, so an allowlist keeps a tampered row from doing that.
"""
from __future__ import annotations

import enum
import inspect
import logging
import os
from collections.abc import Mapping

from pydantic import BaseModel

log = logging.getLogger("fssai.agents")

_LOCK_KEY = 0x46535341  # "FSSA": one advisory lock, so N workers starting together run the migrations once


def _env(environ: Mapping[str, str], name: str) -> str:
    return environ.get(name, "").split("#", 1)[0].strip()


def schema_types() -> list[type]:
    """Every Pydantic model and enum in fssai_contracts.schemas: the only classes a checkpoint may contain."""
    from fssai_contracts import schemas
    return [obj for _, obj in inspect.getmembers(schemas, inspect.isclass)
            if obj.__module__ == schemas.__name__ and issubclass(obj, (BaseModel, enum.Enum))]


def serializer():
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    return JsonPlusSerializer(allowed_msgpack_modules=schema_types())


def from_env(environ: Mapping[str, str] | None = None):
    """The checkpointer PIPELINE_CHECKPOINTS asks for, or None. A wrong value fails here, at worker start-up. An
    unreachable database turns checkpoints off with a warning instead: like the stores' memory fallback, the worker
    must still start and serve runs (a run then restarts from the beginning if its worker dies)."""
    environ = os.environ if environ is None else environ
    mode = _env(environ, "PIPELINE_CHECKPOINTS").lower()
    if mode in ("", "0", "off", "none", "false"):
        return None
    if mode == "memory":
        from langgraph.checkpoint.memory import InMemorySaver
        return InMemorySaver(serde=serializer())
    if mode == "postgres":
        return postgres(_env(environ, "PIPELINE_CHECKPOINT_URL") or _env(environ, "DATABASE_URL"))
    raise RuntimeError(f"PIPELINE_CHECKPOINTS must be empty, 'memory' or 'postgres', not '{mode}'")


def postgres(url: str):
    if not url:
        raise RuntimeError("PIPELINE_CHECKPOINTS=postgres needs PIPELINE_CHECKPOINT_URL or DATABASE_URL")
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(url, min_size=1, max_size=4, open=False, name="fssai-checkpoints",
                          kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
    try:
        pool.open(wait=True, timeout=15)
        saver = PostgresSaver(pool, serde=serializer())
        with pool.connection() as conn:  # held while setup() migrates on another pooled connection
            conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
            try:
                saver.setup()
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    except Exception as exc:  # noqa: BLE001 - any database problem: run without checkpoints, say so once
        pool.close()
        log.warning('{"event": "checkpoints_off", "reason": "%s"}', type(exc).__name__)
        return None
    log.info('{"event": "checkpoints_on", "saver": "postgres"}')
    return saver
