"""Feedback on finished runs, persisted and aggregated (owner Vihaan; L6).

    POST /v1/runs/{run_id}/feedback   {satisfactory, reason}  -> 201 Feedback
    GET  /v1/feedback/summary?days=   satisfactory rate overall, by route, by day; reasons grouped

Each record also keeps the run's route at the time of feedback, so the summary can say *which kind* of answer
reviewers were unhappy with. Store: Postgres table `feedback` (deploy/postgres/init/21-vihaan-feedback.sql) when
DATABASE_URL reaches a database that has it, else in memory (local runs, tests). FEEDBACK_STORE=memory|postgres
forces one. The quality dashboard (observability/grafana/dashboards/quality.json) reads the same table.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from collections import Counter as Tally
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from prometheus_client import Counter
from pydantic import BaseModel, Field

from fssai_contracts.schemas import Feedback, RunState, utcnow

log = logging.getLogger("fssai.api.feedback")
router = APIRouter(prefix="/v1", tags=["feedback"])

FEEDBACK = Counter("fssai_feedback_total", "Feedback received on runs", ["satisfactory", "route"])
RunId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="32-character hex run id")]


class FeedbackIn(BaseModel):
    satisfactory: bool
    reason: str = Field(min_length=1, max_length=2000, description="Why; free text, shown to the team")
    run_id: str | None = Field(None, description="Optional; must match the path if given")


class FeedbackRecord(Feedback):
    feedback_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    route: str | None = None
    client_id: str | None = None


class RateRow(BaseModel):
    total: int
    satisfactory: int
    rate: float | None


class DayRow(RateRow):
    day: date


class ReasonRow(BaseModel):
    reason: str
    count: int
    unsatisfactory: int


class FeedbackSummary(BaseModel):
    days: int
    overall: RateRow
    by_route: dict[str, RateRow]
    by_day: list[DayRow]
    top_reasons: list[ReasonRow]


# ---------------------------------------------------------------- stores

class MemoryFeedbackStore:
    kind = "memory"

    def __init__(self) -> None:
        self._rows: list[FeedbackRecord] = []
        self._lock = threading.Lock()

    def add(self, rec: FeedbackRecord) -> None:
        with self._lock:
            self._rows.append(rec)

    def since(self, start: datetime) -> list[FeedbackRecord]:
        with self._lock:
            return [r for r in self._rows if r.submitted_at >= start]


_INSERT = """INSERT INTO feedback (feedback_id, run_id, satisfactory, reason, route, client_id, submitted_at)
             VALUES (%s, %s, %s, %s, %s, %s, %s)"""
_SINCE = """SELECT feedback_id, run_id, satisfactory, reason, route, client_id, submitted_at
            FROM feedback WHERE submitted_at >= %s ORDER BY submitted_at"""


class PostgresFeedbackStore:
    kind = "postgres"

    def __init__(self, url: str) -> None:
        from psycopg_pool import ConnectionPool
        self.pool = ConnectionPool(url, min_size=0, max_size=2, timeout=3, kwargs={"connect_timeout": 3}, open=True)

    def add(self, rec: FeedbackRecord) -> None:
        with self.pool.connection() as conn:
            conn.execute(_INSERT, (rec.feedback_id, rec.run_id, rec.satisfactory, rec.reason, rec.route,
                                   rec.client_id, rec.submitted_at))

    def since(self, start: datetime) -> list[FeedbackRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(_SINCE, (start,)).fetchall()
        return [FeedbackRecord(feedback_id=r[0], run_id=r[1], satisfactory=r[2], reason=r[3], route=r[4],
                               client_id=r[5], submitted_at=r[6]) for r in rows]


def _env(name: str) -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip()


def store_from_env():
    backend, url = (_env("FEEDBACK_STORE") or "auto").lower(), _env("DATABASE_URL")
    if backend == "memory" or not url:
        return MemoryFeedbackStore()
    if backend == "auto":
        try:
            import psycopg
            with psycopg.connect(url, connect_timeout=2) as conn:
                conn.execute("SELECT 1 FROM feedback LIMIT 1")
        except Exception as exc:  # noqa: BLE001 - no database or no table here: keep feedback in memory
            log.warning("feedback store: postgres unavailable (%s), using memory", type(exc).__name__)
            return MemoryFeedbackStore()
    return PostgresFeedbackStore(url)


_STORE_LOCK = threading.Lock()


def _store(request: Request):
    """One store per app, built on first use (the app factory knows nothing about feedback)."""
    state = request.app.state
    with _STORE_LOCK:
        if getattr(state, "feedback_store", None) is None:
            state.feedback_store = store_from_env()
    return state.feedback_store


# ---------------------------------------------------------------- aggregation

def _rate(rows: list[FeedbackRecord]) -> RateRow:
    ok = sum(r.satisfactory for r in rows)
    return RateRow(total=len(rows), satisfactory=ok, rate=round(ok / len(rows), 4) if rows else None)


def _reason_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%-]", " ", text.lower())).strip()[:120] or "(blank)"


def summarise(rows: list[FeedbackRecord], days: int) -> FeedbackSummary:
    by_route: dict[str, list[FeedbackRecord]] = {}
    by_day: dict[date, list[FeedbackRecord]] = {}
    for r in rows:
        by_route.setdefault(r.route or "unknown", []).append(r)
        by_day.setdefault(r.submitted_at.date(), []).append(r)
    counts = Tally(_reason_key(r.reason) for r in rows)
    bad = Tally(_reason_key(r.reason) for r in rows if not r.satisfactory)
    return FeedbackSummary(
        days=days, overall=_rate(rows),
        by_route={k: _rate(v) for k, v in sorted(by_route.items())},
        by_day=[DayRow(day=d, **_rate(v).model_dump()) for d, v in sorted(by_day.items())],
        top_reasons=[ReasonRow(reason=k, count=n, unsatisfactory=bad[k]) for k, n in counts.most_common(10)])


# ---------------------------------------------------------------- routes

def _problem(status: int, detail: str, request: Request) -> JSONResponse:
    return JSONResponse({"detail": detail, "correlation_id": getattr(request.state, "correlation_id", None)},
                        status_code=status)


@router.post("/runs/{run_id}/feedback", status_code=201, response_model=FeedbackRecord,
             summary="Say whether a run's answer was satisfactory",
             responses={404: {"description": "No such run"}, 409: {"description": "The run has not finished"},
                        422: {"description": "Invalid body"}, 503: {"description": "Feedback store unavailable"}})
async def post_feedback(request: Request, run_id: RunId, body: FeedbackIn):
    if body.run_id and body.run_id != run_id:
        return _problem(422, "run_id in the body does not match the path.", request)
    status = await run_in_threadpool(request.app.state.run_store.get, run_id)
    if status is None:
        return _problem(404, "No run with this id.", request)
    if status.state not in (RunState.COMPLETED, RunState.FAILED):
        return _problem(409, "The run has not finished yet; give feedback once it has.", request)
    rec = FeedbackRecord(run_id=run_id, satisfactory=body.satisfactory, reason=body.reason.strip(),
                         route=status.result.routing.route.value if status.result else None,
                         client_id=(request.headers.get("X-Client-Id") or "")[:64] or None, submitted_at=utcnow())
    try:
        await run_in_threadpool(_store(request).add, rec)
    except Exception as exc:  # noqa: BLE001 - an honest error, not a stack trace
        log.warning("feedback write failed: %s: %s", type(exc).__name__, exc)
        return _problem(503, "Feedback could not be saved. Try again shortly.", request)
    FEEDBACK.labels(str(rec.satisfactory).lower(), rec.route or "unknown").inc()
    return JSONResponse(rec.model_dump(mode="json"), status_code=201)


@router.get("/feedback/summary", response_model=FeedbackSummary, summary="Feedback aggregated",
            responses={503: {"description": "Feedback store unavailable"}})
async def feedback_summary(request: Request, days: int = Query(30, ge=1, le=365)):
    start = utcnow() - timedelta(days=days)
    try:
        rows = await run_in_threadpool(_store(request).since, start)
    except Exception as exc:  # noqa: BLE001 - an honest error, not a stack trace
        log.warning("feedback read failed: %s: %s", type(exc).__name__, exc)
        return _problem(503, "Feedback could not be read. Try again shortly.", request)
    return summarise(rows, days)
