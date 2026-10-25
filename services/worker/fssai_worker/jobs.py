"""execute_run: the unit of work behind every run id.

The worker holds no per-run state of its own (A7): everything it needs is in the job payload,
and everything it produces goes to the RunStore.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from fssai_observability import attach_trace_context, inject_trace_context, span

from fssai_contracts.context import RunContext
from fssai_contracts.registry import build
from fssai_contracts.schemas import LabelCheckRequest, RunState, RunStatus, utcnow

log = logging.getLogger("fssai.worker")

RUNS_FINISHED = Counter("fssai_runs_finished_total", "Runs finished by the worker",
                        ["state", "route", "complete"])
RUN_SECONDS = Histogram("fssai_run_duration_seconds", "Wall-clock time of a run inside the worker",
                        buckets=(0.5, 1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180))


@dataclass
class Deps:
    pipeline: object
    run_store: object


@lru_cache(maxsize=1)
def default_deps() -> Deps:
    """Built once per worker process from IMPL_* (fakes when unset)."""
    return Deps(pipeline=build("pipeline"), run_store=build("run_store"))


def payload_for(run_id: str, correlation_id: str, request: LabelCheckRequest) -> dict:
    """What travels on the queue: plain JSON, so any worker can pick it up. `trace` carries the caller's
    OpenTelemetry context (empty when tracing is off), so the run continues the API's trace (D5)."""
    return {"run_id": run_id, "correlation_id": correlation_id, "request": request.model_dump(mode="json"),
            "trace": inject_trace_context()}


def execute_run(payload: dict, deps: Deps | None = None) -> str:
    """Run one label check and save the outcome. Returns the final state. Never raises for a bad run:
    a failure is saved as RunState.FAILED so the client sees it when polling."""
    with attach_trace_context(payload.get("trace")), \
            span("worker.execute_run", run_id=payload["run_id"], correlation_id=payload["correlation_id"]):
        return _execute(payload, deps or default_deps())


def _execute(payload: dict, deps: Deps) -> str:
    run_id, correlation_id = payload["run_id"], payload["correlation_id"]
    ctx = RunContext.new(run_id=run_id, correlation_id=correlation_id)
    store = deps.run_store
    status = store.get(run_id) or RunStatus(run_id=run_id, state=RunState.QUEUED, submitted_at=utcnow(),
                                            updated_at=utcnow(), correlation_id=correlation_id)
    status = status.model_copy(update={"state": RunState.RUNNING, "updated_at": utcnow()})
    store.save(status)
    ctx.event("run_started")
    t0 = time.monotonic()
    try:
        request = LabelCheckRequest.model_validate(payload["request"])
        result = deps.pipeline.run(request, ctx)
    except ValidationError as exc:  # the gate already validated it; a mismatch here is a bug, not user error
        final = status.model_copy(update={"state": RunState.FAILED, "updated_at": utcnow(),
                                          "error": f"invalid job payload: {exc.error_count()} validation error(s)"})
    except Exception as exc:  # noqa: BLE001 - any pipeline crash must still end the run visibly
        log.exception("run %s crashed", run_id)
        ctx.event("run_crashed", error_type=type(exc).__name__)
        final = status.model_copy(update={"state": RunState.FAILED, "updated_at": utcnow(),
                                          "error": f"internal error ({type(exc).__name__})"})
    else:
        final = status.model_copy(update={"state": RunState.COMPLETED, "updated_at": utcnow(), "result": result})
    store.save(final)

    route = final.result.routing.route.value if final.result else "none"
    complete = str(final.result.complete).lower() if final.result else "false"
    RUNS_FINISHED.labels(final.state.value, route, complete).inc()
    RUN_SECONDS.observe(time.monotonic() - t0)
    ctx.event("run_finished", state=final.state.value, route=route, complete=complete,
              duration_ms=round((time.monotonic() - t0) * 1000, 1))
    return final.state.value
