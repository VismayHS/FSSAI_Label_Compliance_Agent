"""execute_run and the two dispatch modes. Redis is fakeredis; the pipeline is the contracts' fakes."""
from __future__ import annotations

import fakeredis
import pytest
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty

from fssai_contracts.fakes import InMemoryRunStore
from fssai_contracts.pipeline import ReferencePipeline
from fssai_contracts.schemas import LabelCheckRequest, Route, RunState, RunStatus, utcnow
from fssai_worker import dispatch, jobs
from fssai_worker.jobs import Deps, execute_run, payload_for


def request(protein_g: float = 12.0) -> LabelCheckRequest:
    return LabelCheckRequest.model_validate({
        "declared_category": "demo-category",
        "package": {"net_quantity": 200, "net_quantity_unit": "g", "principal_display_panel_cm2": 120},
        "label": {"product_name": "Roasted chana", "claims": ["Source of protein"],
                  "allergen_statement": "Contains: chickpea"},
        "nutrition": {"basis": "per_100g", "energy_kcal": 380, "protein_g": protein_g, "carbohydrate_g": 55,
                      "total_sugars_g": 3, "total_fat_g": 6},
    })


def deps() -> Deps:
    return Deps(pipeline=ReferencePipeline.from_registry(), run_store=InMemoryRunStore())


def queued(d: Deps, run_id: str = "run-1") -> RunStatus:
    status = RunStatus(run_id=run_id, state=RunState.QUEUED, submitted_at=utcnow(), updated_at=utcnow(),
                       client_id="analyst-1")
    d.run_store.save(status)
    return status


def test_execute_run_saves_completed_result_and_keeps_submission_fields():
    d = deps()
    submitted = queued(d)
    assert execute_run(payload_for("run-1", "corr-1", request(12.0)), d) == "completed"
    saved = d.run_store.get("run-1")
    assert saved.state == RunState.COMPLETED and saved.client_id == "analyst-1"
    assert saved.submitted_at == submitted.submitted_at and saved.updated_at >= submitted.updated_at
    assert saved.result.routing.route == Route.CLEAR_FOR_PRINT
    assert saved.result.correlation_id == "corr-1" and saved.result.steps


def test_protein_below_the_condition_routes_to_revise():
    d = deps()
    queued(d)
    execute_run(payload_for("run-1", "c", request(4.0)), d)
    assert d.run_store.get("run-1").result.routing.route == Route.REVISE_AND_RECHECK


def test_a_crashing_pipeline_ends_the_run_as_failed_without_raising():
    class Boom:
        def run(self, request, ctx):
            raise KeyError("secret detail")

    d = Deps(pipeline=Boom(), run_store=InMemoryRunStore())
    queued(d)
    assert execute_run(payload_for("run-1", "c", request()), d) == "failed"
    saved = d.run_store.get("run-1")
    assert saved.state == RunState.FAILED and saved.error == "internal error (KeyError)"
    assert "secret detail" not in saved.error  # no internals leak to the client


def test_an_invalid_payload_fails_the_run():
    d = deps()
    queued(d)
    assert execute_run({"run_id": "run-1", "correlation_id": "c", "request": {"oops": 1}}, d) == "failed"
    assert d.run_store.get("run-1").error.startswith("invalid job payload")


def test_a_run_unknown_to_the_store_is_still_executed_and_saved():
    d = deps()
    execute_run(payload_for("run-9", "c", request()), d)
    assert d.run_store.get("run-9").state == RunState.COMPLETED


def test_inline_dispatcher_executes_in_the_background():
    d = deps()
    queued(d)
    future = dispatch.InlineDispatcher(d).submit(payload_for("run-1", "c", request()))
    assert future.result(timeout=10) == "completed"
    assert d.run_store.get("run-1").state == RunState.COMPLETED


def test_queue_dispatcher_enqueues_and_an_rq_worker_executes_it(monkeypatch):
    redis = fakeredis.FakeRedis()
    d = deps()
    queued(d)
    monkeypatch.setattr(jobs, "default_deps", lambda: d)  # the worker process builds its deps itself
    dispatcher = dispatch.QueueDispatcher(redis, job_timeout_s=120)
    assert dispatcher.submit(payload_for("run-1", "c", request())) is None

    queue = Queue(dispatch.QUEUE_NAME, connection=redis)
    [job] = queue.jobs
    assert job.id == "run-1" and job.func_name == dispatch.JOB_FUNC and job.timeout == 120
    assert d.run_store.get("run-1").state == RunState.QUEUED  # nothing ran yet

    worker = SimpleWorker([queue], connection=redis)
    worker.death_penalty_class = TimerDeathPenalty
    worker.work(burst=True)
    assert d.run_store.get("run-1").state == RunState.COMPLETED
    assert dispatcher.ready()[0] is True


def test_from_env_picks_the_mode_and_rejects_unknown_ones():
    assert dispatch.from_env({}, deps()).mode == "inline"
    assert dispatch.from_env({"RUN_DISPATCH": "queue  # comment", "REDIS_URL": "redis://localhost:1/0"},
                             deps()).mode == "queue"
    with pytest.raises(RuntimeError, match="RUN_DISPATCH"):
        dispatch.from_env({"RUN_DISPATCH": "kafka"}, deps())


def test_queue_dispatcher_is_not_ready_when_redis_is_down():
    import redis as redis_lib
    conn = redis_lib.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    ok, reason = dispatch.QueueDispatcher(conn, job_timeout_s=60).ready()
    assert not ok and "unreachable" in reason
