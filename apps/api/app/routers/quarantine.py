"""Quarantine: the requests the gate rejected, with their field errors (owner Vihaan; D1, F2, demo #4).

    GET /v1/quarantine?limit=&client_id=&code=   newest first
    GET /v1/quarantine/{quarantine_id}           one record, with the evidence that no run was started for it

Reads `request.app.state.gate.quarantine`: the real gate's store (fssai_gate.quarantine, Postgres in Compose) or,
before IMPL_GATE is switched on, the fake gate's dict. A rejected request never has a run: the API saves a run
only after an accepted gate decision (app/routers/runs.py), and there is no link from a quarantine record to
any run id because none is ever created.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fssai_contracts.schemas import FieldError

router = APIRouter(prefix="/v1", tags=["quarantine"])

QuarantineId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="32-character hex quarantine id")]


class QuarantineEntry(BaseModel):
    quarantine_id: str
    received_at: datetime | None = None
    client_id: str | None = None
    schema_version: str | None = None
    error_count: int
    errors: list[FieldError]
    payload: object = None


class QuarantineList(BaseModel):
    count: int
    store: str = Field(description="Where rejects are kept: postgres, memory or fake")
    items: list[QuarantineEntry]


class QuarantineEvidence(BaseModel):
    run_created: bool = Field(description="Always false: a rejected request never becomes a run")
    runs_checked: int = Field(description="How many recent runs were searched for this request")
    note: str


class QuarantineDetail(QuarantineEntry):
    evidence: QuarantineEvidence


def _entries(store, limit: int) -> tuple[str, list[QuarantineEntry]]:
    if store is None:
        return "none", []
    if hasattr(store, "recent"):  # fssai_gate stores
        kind = "postgres" if hasattr(store, "pool") else "memory"
        return kind, [QuarantineEntry(quarantine_id=r.quarantine_id, received_at=r.received_at, client_id=r.client_id,
                                      schema_version=r.schema_version, error_count=len(r.errors), errors=r.errors,
                                      payload=r.payload) for r in store.recent(limit)]
    if isinstance(store, dict):  # FakeRequestGate: {qid: {raw, client_id, errors}}, insertion ordered
        items = list(store.items())[::-1][:limit]
        return "fake", [QuarantineEntry(quarantine_id=qid, client_id=v.get("client_id"), payload=v.get("raw"),
                                        errors=[FieldError(**e) for e in v.get("errors", [])],
                                        error_count=len(v.get("errors", []))) for qid, v in items]
    return "unknown", []


def _store(request: Request):
    return getattr(request.app.state.gate, "quarantine", None)


def _problem(status: int, detail: str, request: Request) -> JSONResponse:
    return JSONResponse({"detail": detail, "correlation_id": getattr(request.state, "correlation_id", None)},
                        status_code=status)


@router.get("/quarantine", response_model=QuarantineList, summary="Rejected requests, newest first",
            description="Every request the ingestion gate rejected, with all its field errors and the raw payload. "
                        "Rate-limited requests are not here: they were not malformed.")
async def list_quarantine(request: Request, limit: int = Query(20, ge=1, le=100),
                          client_id: str | None = Query(None, max_length=64),
                          code: str | None = Query(None, max_length=32, description="Only records with this error code")):
    scan = limit if not (client_id or code) else 100  # filter within the 100 newest
    kind, items = await run_in_threadpool(_entries, _store(request), scan)
    if client_id:
        items = [i for i in items if i.client_id == client_id]
    if code:
        items = [i for i in items if any(e.code == code for e in i.errors)]
    return QuarantineList(count=len(items[:limit]), store=kind, items=items[:limit])


@router.get("/quarantine/{quarantine_id}", response_model=QuarantineDetail, summary="One rejected request",
            responses={404: {"description": "No quarantine record with this id"}})
async def get_quarantine(request: Request, quarantine_id: QuarantineId):
    store = _store(request)
    kind, items = await run_in_threadpool(_entries, store, 100)
    entry = next((i for i in items if i.quarantine_id == quarantine_id), None)
    if entry is None and hasattr(store, "get"):
        rec = await run_in_threadpool(store.get, quarantine_id)
        if rec is not None:
            entry = QuarantineEntry(quarantine_id=rec.quarantine_id, received_at=rec.received_at,
                                    client_id=rec.client_id, schema_version=rec.schema_version,
                                    error_count=len(rec.errors), errors=rec.errors, payload=rec.payload)
    if entry is None:
        return _problem(404, "No quarantine record with this id.", request)
    try:
        recent = await run_in_threadpool(request.app.state.run_store.recent, 100)
    except Exception:  # noqa: BLE001 - the record itself is still worth returning
        recent = []
    same = [r.run_id for r in recent if r.request is not None and isinstance(entry.payload, dict)
            and r.request.model_dump(mode="json") == entry.payload]
    evidence = QuarantineEvidence(
        run_created=bool(same), runs_checked=len(recent),
        note="No run was created for this request: the API saves a run and enqueues a job only after the gate "
             "accepts a request." if not same else f"Unexpected: runs {same} carry this payload.")
    return QuarantineDetail(**entry.model_dump(), evidence=evidence)
