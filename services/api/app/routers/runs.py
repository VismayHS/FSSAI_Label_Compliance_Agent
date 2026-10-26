"""Runs: submit (202 + run id), poll status, read the trace, list recent runs (A4, F1, D1, D5).

Order on submit, so a malformed request can never start an agent run (D1, demo #4):
    client id check -> size limit -> gate (rate limit, validate, quarantine) -> save QUEUED -> dispatch
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Header, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from fssai_observability import span
from prometheus_client import Counter

from fssai_contracts.schemas import FieldError, RunState, RunStatus, utcnow
from fssai_worker import webhook
from fssai_worker.jobs import payload_for

from ..models import AgentRollup, Problem, RateLimited, RunAccepted, RunRejected, RunSummary, RunTrace
from ..observability import event

router = APIRouter(prefix="/v1", tags=["runs"])

RUNS_SUBMITTED = Counter("fssai_runs_submitted_total", "Run submissions by outcome", ["outcome"])

_CLIENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
RunId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="32-character hex run id")]


def _problem(status: int, detail: str, request: Request) -> JSONResponse:
    return JSONResponse(Problem(detail=detail, correlation_id=request.state.correlation_id).model_dump(),
                        status_code=status)


def _jaeger_url(run_id: str) -> str | None:
    """A Jaeger search for this run's spans (the worker tags them with run_id). None when tracing is off."""
    base = os.environ.get("JAEGER_UI_URL", "").split("#", 1)[0].strip().rstrip("/")
    if not base or not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").split("#", 1)[0].strip():
        return None
    return f"{base}/search?" + urlencode({"service": "worker", "tags": json.dumps({"run_id": run_id})})


def _parse(body: bytes) -> tuple[dict, list[FieldError]]:
    """The gate takes a dict. Non-JSON or non-object bodies still go through it, wrapped, so they are
    quarantined like any other reject instead of being dropped by the framework."""
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ({"_unparseable_body": body[:2000].decode("utf-8", "replace")},
                [FieldError(loc="body", message="Request body is not valid JSON.", code="json_invalid")])
    if not isinstance(parsed, dict):
        return ({"_non_object_body": parsed},
                [FieldError(loc="body", message="Request body must be a JSON object.", code="type")])
    return parsed, []


@router.post(
    "/runs", status_code=202, response_model=RunAccepted, summary="Submit a label for checking",
    description="Validates the request at the ingestion boundary and returns a run id at once. Poll "
                "`status_url` until `state` is `completed` or `failed`. The body is a `LabelCheckRequest`.",
    responses={400: {"model": Problem}, 413: {"model": Problem}, 422: {"model": RunRejected},
               429: {"model": RateLimited}, 503: {"model": Problem}},
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {
        "schema": {"$ref": "#/components/schemas/LabelCheckRequest"}}}}},
)
async def submit_run(request: Request, x_client_id: str | None = Header(None, description="Caller id, used for rate limiting"),
                     x_callback_url: str | None = Header(None, description="Optional: POSTed a run-finished notice "
                                                         "when the run ends. Only hosts in WEBHOOK_ALLOWED_HOSTS.")):
    state = request.app.state
    cid = request.state.correlation_id
    if not x_client_id or not _CLIENT_ID.match(x_client_id):
        return _problem(400, "Header X-Client-Id is required: 1-64 letters, digits or . _ : -", request)
    if x_callback_url is not None and (problem := webhook.check_url(x_callback_url)):
        return _problem(400, problem, request)  # before the gate: a bad callback is the caller's setup, not data

    limit = state.settings.max_request_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return _problem(413, f"Request body is larger than {limit} bytes.", request)
    body = await request.body()
    if len(body) > limit:
        return _problem(413, f"Request body is larger than {limit} bytes.", request)

    raw, body_errors = _parse(body)
    decision = await run_in_threadpool(state.gate.check, raw, x_client_id)

    if decision.rate_limited:
        RUNS_SUBMITTED.labels("rate_limited").inc()
        retry = decision.retry_after_s or 1.0
        event("run_rate_limited", correlation_id=cid, client_id=x_client_id, retry_after_s=retry)
        return JSONResponse(RateLimited(detail="Too many requests for this client.", retry_after_s=retry,
                                        correlation_id=cid).model_dump(),
                            status_code=429, headers={"Retry-After": str(math.ceil(retry))})

    if not decision.accepted or body_errors or decision.request is None:
        RUNS_SUBMITTED.labels("rejected").inc()
        errors = body_errors + decision.errors
        event("run_rejected", correlation_id=cid, client_id=x_client_id, quarantine_id=decision.quarantine_id,
              error_count=len(errors))
        return JSONResponse(RunRejected(errors=errors, quarantine_id=decision.quarantine_id,
                                        correlation_id=cid).model_dump(), status_code=422)

    run_id = uuid.uuid4().hex
    now = utcnow()
    status = RunStatus(run_id=run_id, state=RunState.QUEUED, submitted_at=now, updated_at=now,
                       client_id=x_client_id, correlation_id=cid, request=decision.request)
    await run_in_threadpool(state.run_store.save, status)
    try:
        with span("api.submit_run", run_id=run_id, correlation_id=cid, client_id=x_client_id):
            payload = payload_for(run_id, cid, decision.request,  # carries this span's context to the worker
                                  callback_url=x_callback_url)
        await run_in_threadpool(state.dispatcher.submit, payload)
    except Exception as exc:  # noqa: BLE001 - the queue being down must end as an honest error
        failed = status.model_copy(update={"state": RunState.FAILED, "updated_at": utcnow(),
                                           "error": "could not queue the run; try again"})
        await run_in_threadpool(state.run_store.save, failed)
        RUNS_SUBMITTED.labels("queue_error").inc()
        event("run_queue_error", correlation_id=cid, run_id=run_id, error_type=type(exc).__name__)
        return _problem(503, "The run queue is unavailable. Try again shortly.", request)

    RUNS_SUBMITTED.labels("accepted").inc()
    event("run_accepted", correlation_id=cid, run_id=run_id, client_id=x_client_id, dispatch=state.dispatcher.mode)
    accepted = RunAccepted(run_id=run_id, status_url=f"/v1/runs/{run_id}", trace_url=f"/v1/runs/{run_id}/trace",
                           correlation_id=cid)
    return JSONResponse(accepted.model_dump(), status_code=202, headers={"Location": accepted.status_url})


@router.get("/runs", response_model=list[RunSummary], summary="Recent runs, newest first")
async def list_runs(request: Request, limit: int = Query(20, ge=1, le=100)) -> list[RunSummary]:
    runs = await run_in_threadpool(request.app.state.run_store.recent, limit)
    return [RunSummary(run_id=r.run_id, state=r.state, submitted_at=r.submitted_at, updated_at=r.updated_at,
                       product_name=r.request.label.product_name if r.request else None,
                       route=r.result.routing.route if r.result else None,
                       complete=r.result.complete if r.result else None) for r in runs]


@router.get("/runs/{run_id}", response_model=RunStatus, summary="Poll a run",
            responses={404: {"model": Problem}})
async def get_run(request: Request, run_id: RunId):
    status = await run_in_threadpool(request.app.state.run_store.get, run_id)
    if status is None:
        return _problem(404, "No run with this id.", request)
    return status


@router.get("/runs/{run_id}/trace", response_model=RunTrace, summary="Reconstruct a run step by step",
            responses={404: {"model": Problem}})
async def get_trace(request: Request, run_id: RunId):
    status: RunStatus | None = await run_in_threadpool(request.app.state.run_store.get, run_id)
    if status is None:
        return _problem(404, "No run with this id.", request)
    result = status.result
    trace = RunTrace(run_id=status.run_id, correlation_id=status.correlation_id, state=status.state,
                     submitted_at=status.submitted_at, updated_at=status.updated_at, request=status.request,
                     error=status.error, jaeger_url=_jaeger_url(status.run_id))
    if result is None:
        return trace
    agents: dict[str, AgentRollup] = {}
    for s in result.steps:
        a = agents.setdefault(s.agent, AgentRollup())
        a.steps += 1
        a.tool_calls += s.kind == "tool"
        a.llm_calls += s.kind == "llm"
        a.errors += s.error is not None
        a.latency_ms = round(a.latency_ms + s.latency_ms, 1)
        a.prompt_tokens += s.prompt_tokens
        a.completion_tokens += s.completion_tokens
        a.cost_usd = round(a.cost_usd + s.cost_usd, 8)
    first = result.steps[0].started_at if result.steps else None
    return trace.model_copy(update={
        "queue_wait_ms": round((first - status.submitted_at).total_seconds() * 1000, 1) if first else None,
        "complete": result.complete, "classification": result.classification, "findings": result.findings,
        "verdict": result.verdict, "routing": result.routing, "guardrails": result.guardrails,
        "prompt_versions": result.prompt_versions, "totals": result.totals, "agents": agents,
        "steps": result.steps, "notice": result.notice})


def _env_s(name: str, default: float) -> float:
    raw = os.environ.get(name, "").split("#", 1)[0].strip()
    return float(raw) if raw else default


@router.get("/runs/{run_id}/events", summary="Follow a run live (server-sent events)",
            description="A `text/event-stream` instead of polling: an `event: status` with the full `RunStatus` "
                        "every time the run changes, then `event: end` once it is completed or failed. Comment "
                        "lines are keep-alives. Clients without EventSource keep polling `GET /v1/runs/{run_id}`.",
            responses={200: {"content": {"text/event-stream": {}}}, 404: {"model": Problem}})
async def run_events(request: Request, run_id: RunId):
    store = request.app.state.run_store
    first = await run_in_threadpool(store.get, run_id)
    if first is None:
        return _problem(404, f"No run with id {run_id}.", request)
    poll_s = _env_s("SSE_POLL_S", 0.5)
    # Never hold a connection longer than a run can last (RUN_MAX_WALL_S) plus time in the queue.
    deadline = time.monotonic() + _env_s("RUN_MAX_WALL_S", 90.0) + _env_s("SSE_QUEUE_GRACE_S", 300.0)

    async def stream():
        status, last, quiet = first, None, 0.0
        while True:
            key = (status.state, status.updated_at)
            if key != last:
                yield f"event: status\ndata: {status.model_dump_json()}\n\n"
                last, quiet = key, 0.0
            if status.state in (RunState.COMPLETED, RunState.FAILED):
                yield "event: end\ndata: {}\n\n"
                return
            if await request.is_disconnected() or time.monotonic() > deadline:
                return
            await asyncio.sleep(poll_s)
            quiet += poll_s
            if quiet >= 15:  # under nginx's 30 s read timeout on the web proxy
                yield ": keep-alive\n\n"
                quiet = 0.0
            status = await run_in_threadpool(store.get, run_id) or status

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
