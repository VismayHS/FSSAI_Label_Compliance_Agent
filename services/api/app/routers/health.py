"""Liveness, readiness and Prometheus metrics (F8). Every HTTP service exposes these three."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from fssai_contracts.fakes import InMemoryRunStore

router = APIRouter(tags=["operations"])


@router.get("/healthz", summary="Liveness: the process is up")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness: dependencies reachable and the configuration is usable")
async def readyz(request: Request) -> JSONResponse:
    state = request.app.state
    checks: dict[str, dict] = {}

    ok, detail = await run_in_threadpool(state.dispatcher.ready)
    checks["dispatch"] = {"ok": ok, "detail": detail}

    try:
        await run_in_threadpool(state.run_store.recent, 1)
        store_ok, store_detail = True, type(state.run_store).__name__
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        store_ok, store_detail = False, f"unreachable: {type(exc).__name__}"
    if store_ok and state.dispatcher.mode == "queue" and isinstance(state.run_store, InMemoryRunStore):
        # Workers are other processes: they can't see this process's memory, so runs would never finish.
        store_ok, store_detail = False, "queue mode needs a shared run store; set IMPL_RUN_STORE"
    checks["run_store"] = {"ok": store_ok, "detail": store_detail}

    ready = all(c["ok"] for c in checks.values())
    return JSONResponse({"ready": ready, "checks": checks}, status_code=200 if ready else 503)


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
