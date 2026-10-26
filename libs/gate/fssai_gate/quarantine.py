"""Quarantine: every rejected request is stored *with* its errors instead of being discarded (D1, glossary).

Two stores behind one small interface: InMemoryQuarantine (tests, local runs) and PostgresQuarantine (Compose;
table from deploy/postgres/init/20-vihaan-quarantine.sql). The quarantine router (GET /v1/quarantine) reads
them through `app.state.gate.quarantine`.
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from fssai_contracts.schemas import FieldError, utcnow

log = logging.getLogger("fssai.gate")


class QuarantineRecord(BaseModel):
    quarantine_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    received_at: datetime = Field(default_factory=utcnow)
    client_id: str
    correlation_id: str | None = None
    errors: list[FieldError]
    payload: object = None            # the raw request exactly as received (a dict, or the wrapped non-JSON body)
    schema_version: str | None = None


class QuarantineStore(Protocol):
    def put(self, record: QuarantineRecord) -> str: ...

    def get(self, quarantine_id: str) -> QuarantineRecord | None: ...

    def recent(self, limit: int = 50) -> list[QuarantineRecord]: ...


class InMemoryQuarantine:
    """Bounded (oldest dropped first) so a flood of bad requests cannot exhaust memory."""

    def __init__(self, max_records: int = 10_000) -> None:
        self._records: OrderedDict[str, QuarantineRecord] = OrderedDict()
        self._lock = threading.Lock()
        self.max_records = max_records

    def put(self, record: QuarantineRecord) -> str:
        with self._lock:
            self._records[record.quarantine_id] = record
            while len(self._records) > self.max_records:
                self._records.popitem(last=False)
        return record.quarantine_id

    def get(self, quarantine_id: str) -> QuarantineRecord | None:
        return self._records.get(quarantine_id)

    def recent(self, limit: int = 50) -> list[QuarantineRecord]:
        with self._lock:
            return list(reversed(self._records.values()))[:limit]

    def __len__(self) -> int:
        return len(self._records)


_INSERT = """
INSERT INTO quarantine (quarantine_id, received_at, client_id, correlation_id, schema_version,
                        error_count, error_codes, errors, payload)
VALUES (%(quarantine_id)s, %(received_at)s, %(client_id)s, %(correlation_id)s, %(schema_version)s,
        %(error_count)s, %(error_codes)s, %(errors)s, %(payload)s)
ON CONFLICT (quarantine_id) DO NOTHING
"""
_COLUMNS = "quarantine_id, received_at, client_id, correlation_id, schema_version, errors, payload"


class PostgresQuarantine:
    """Writes never raise into the gate: if Postgres is down the record is kept in memory (and logged), so the
    reject still has its evidence and the caller still gets a quarantine id. Reads merge both."""

    def __init__(self, database_url: str, *, max_connections: int = 2, timeout_s: float = 3.0) -> None:
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(database_url, min_size=0, max_size=max_connections, timeout=timeout_s,
                                   kwargs={"connect_timeout": max(1, int(timeout_s))}, open=True)
        self.fallback = InMemoryQuarantine()

    def put(self, record: QuarantineRecord) -> str:
        from psycopg.types.json import Jsonb

        row = {**record.model_dump(exclude={"errors", "payload"}), "error_count": len(record.errors),
               "error_codes": sorted({e.code for e in record.errors}),
               "errors": Jsonb([e.model_dump() for e in record.errors]), "payload": Jsonb(record.payload)}
        try:
            with self.pool.connection() as conn:
                conn.execute(_INSERT, row)
        except Exception as exc:  # noqa: BLE001 - a quarantine write must never turn a reject into a 500
            log.warning("quarantine write failed, kept in memory: %s: %s", type(exc).__name__, exc)
            self.fallback.put(record)
        return record.quarantine_id

    def _rows(self, sql: str, params: tuple) -> list[QuarantineRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [QuarantineRecord(quarantine_id=r[0], received_at=r[1], client_id=r[2], correlation_id=r[3],
                                 schema_version=r[4], errors=r[5], payload=r[6]) for r in rows]

    def _safe_rows(self, sql: str, params: tuple) -> list[QuarantineRecord]:
        try:
            return self._rows(sql, params)
        except Exception as exc:  # noqa: BLE001 - degrade to what this process holds, never a 500
            log.warning("quarantine read failed, showing in-memory records only: %s: %s", type(exc).__name__, exc)
            return []

    def get(self, quarantine_id: str) -> QuarantineRecord | None:
        found = self._safe_rows(f"SELECT {_COLUMNS} FROM quarantine WHERE quarantine_id = %s", (quarantine_id,))
        return found[0] if found else self.fallback.get(quarantine_id)

    def recent(self, limit: int = 50) -> list[QuarantineRecord]:
        rows = self._safe_rows(f"SELECT {_COLUMNS} FROM quarantine ORDER BY received_at DESC LIMIT %s", (limit,))
        merged = sorted([*rows, *self.fallback.recent(limit)], key=lambda r: r.received_at, reverse=True)
        return merged[:limit]

    def close(self) -> None:
        self.pool.close()
