"""Vihaan's API routes (feedback, quarantine) on the real app factory, with the real gate and in-memory stores.

The API auto-mounts every router in services/api/app/routers/, so these tests also prove the files are picked up.
Skipped if the API package is not installed (pip install -e services/api).
"""
import copy

import pytest

pytest.importorskip("app.main")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from fssai_contracts.fakes import FakeRequestGate, InMemoryRunStore  # noqa: E402
from fssai_contracts.pipeline import ReferencePipeline  # noqa: E402
from fssai_gate.gate import RequestGate  # noqa: E402
from fssai_gate.ratelimit import MemoryTokenBucket  # noqa: E402
from fssai_worker.jobs import Deps, execute_run  # noqa: E402

VALID = {
    "declared_category": "breakfast-cereals",
    "package": {"net_quantity": 500, "net_quantity_unit": "g", "principal_display_panel_cm2": 180},
    "label": {"product_name": "Multigrain flakes", "claims": ["Source of protein"], "ingredients": "Wheat, oats",
              "allergen_statement": "Contains: wheat, oats", "veg_status": "veg"},
    "nutrition": {"basis": "per_100g", "energy_kcal": 371, "protein_g": 8, "carbohydrate_g": 78,
                  "total_sugars_g": 12, "total_fat_g": 3},
}


class SyncDispatcher:
    mode = "inline"

    def __init__(self, deps):
        self.deps, self.submitted = deps, []

    def submit(self, payload):
        self.submitted.append(payload)
        execute_run(payload, self.deps)

    def ready(self):
        return True, "test"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("FEEDBACK_STORE", "memory")
    store = InMemoryRunStore()
    dispatcher = SyncDispatcher(Deps(pipeline=ReferencePipeline.from_registry(), run_store=store))
    gate = RequestGate(limiter=MemoryTokenBucket(per_min=60, burst=5))
    app = create_app(gate=gate, run_store=store, dispatcher=dispatcher)
    client = TestClient(app)
    client.store, client.dispatcher, client.gate = store, dispatcher, gate
    return client


def submit(api, body, client_id="analyst-1", **headers):
    return api.post("/v1/runs", json=body, headers={"X-Client-Id": client_id, **headers})


# ---------------------------------------------------------------- demo #4: reject, quarantine, no run

def test_malformed_request_is_quarantined_and_starts_no_run(api):
    bad = copy.deepcopy(VALID)
    bad["nutrition"].update(added_sugars_g=20, protein_g="lots")
    bad["label"]["fssai_licence_number"] = "123"
    r = submit(api, bad, **{"X-Correlation-Id": "demo-4"})
    assert r.status_code == 422
    body = r.json()
    codes = {e["code"] for e in body["errors"]}
    assert {"type", "format"} <= codes and body["quarantine_id"]
    assert api.store.recent() == [] and api.dispatcher.submitted == [], "no run row and no job for a reject"

    listed = api.get("/v1/quarantine").json()
    assert listed["store"] == "memory" and listed["items"][0]["quarantine_id"] == body["quarantine_id"]
    assert listed["items"][0]["payload"] == bad and listed["items"][0]["client_id"] == "analyst-1"

    detail = api.get(f"/v1/quarantine/{body['quarantine_id']}").json()
    assert detail["evidence"]["run_created"] is False and detail["error_count"] == len(body["errors"])


def test_valid_request_runs_and_is_not_quarantined(api):
    r = submit(api, VALID)
    assert r.status_code == 202 and len(api.dispatcher.submitted) == 1
    assert api.get("/v1/quarantine").json()["count"] == 0


def test_non_json_body_is_quarantined(api):
    r = api.post("/v1/runs", content=b"{not json", headers={"X-Client-Id": "c", "Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["quarantine_id"]
    assert api.get("/v1/quarantine").json()["items"][0]["payload"] == {"_unparseable_body": "{not json"}


def test_rate_limited_is_429_and_not_quarantined(api):
    codes = [submit(api, {"bad": i}, client_id="flooder").status_code for i in range(7)]
    assert codes[:5] == [422] * 5 and codes[5:] == [429, 429]
    assert api.get("/v1/quarantine", params={"client_id": "flooder"}).json()["count"] == 5
    assert submit(api, VALID, client_id="someone-else").status_code == 202


def test_quarantine_filters_and_404(api):
    submit(api, {**VALID, "declared_category": "Not A Slug"})
    submit(api, {**VALID, "schema_version": "9.0"})
    assert api.get("/v1/quarantine", params={"code": "category"}).json()["count"] == 1
    assert api.get("/v1/quarantine", params={"limit": 1}).json()["count"] == 1
    assert api.get(f"/v1/quarantine/{'0' * 32}").status_code == 404
    assert api.get("/v1/quarantine/not-an-id").status_code == 422


def test_quarantine_works_with_the_fake_gate_too():
    app = create_app(gate=FakeRequestGate(), run_store=InMemoryRunStore(),
                     dispatcher=SyncDispatcher(Deps(pipeline=None, run_store=InMemoryRunStore())))
    client = TestClient(app)
    r = client.post("/v1/runs", json={"declared_category": "x"}, headers={"X-Client-Id": "c"})
    assert r.status_code == 422
    listed = client.get("/v1/quarantine").json()
    assert listed["store"] == "fake" and listed["items"][0]["quarantine_id"] == r.json()["quarantine_id"]


# ---------------------------------------------------------------- feedback (L6)

def finished_run(api, protein=8):
    r = submit(api, {**VALID, "nutrition": {**VALID["nutrition"], "protein_g": protein}})
    return r.json()["run_id"]


def test_feedback_is_stored_with_the_runs_route(api):
    run_id = finished_run(api)
    r = api.post(f"/v1/runs/{run_id}/feedback", json={"satisfactory": False, "reason": "Missed the veg mark"},
                 headers={"X-Client-Id": "reviewer-1"})
    assert r.status_code == 201
    rec = r.json()
    route = api.get(f"/v1/runs/{run_id}").json()["result"]["routing"]["route"]
    assert rec["route"] == route and rec["client_id"] == "reviewer-1" and rec["feedback_id"]


def test_feedback_validation(api):
    run_id = finished_run(api)
    assert api.post(f"/v1/runs/{'a' * 32}/feedback", json={"satisfactory": True, "reason": "x"}).status_code == 404
    assert api.post(f"/v1/runs/{run_id}/feedback", json={"satisfactory": True, "reason": ""}).status_code == 422
    assert api.post(f"/v1/runs/{run_id}/feedback", json={"reason": "no flag"}).status_code == 422
    assert api.post(f"/v1/runs/{run_id}/feedback",
                    json={"satisfactory": True, "reason": "ok", "run_id": "b" * 32}).status_code == 422


def test_feedback_on_an_unfinished_run_is_refused(api):
    from fssai_contracts.schemas import RunState, RunStatus, utcnow
    now = utcnow()
    api.store.save(RunStatus(run_id="c" * 32, state=RunState.QUEUED, submitted_at=now, updated_at=now))
    assert api.post(f"/v1/runs/{'c' * 32}/feedback", json={"satisfactory": True, "reason": "x"}).status_code == 409


def test_summary_rates_by_route_day_and_reason(api):
    a, b = finished_run(api, 8), finished_run(api, 14)
    for run_id, ok, reason in [(a, True, "Correct and cited"), (a, False, "Missed the veg mark!"),
                               (b, False, "missed the  veg mark"), (b, True, "Correct and cited")]:
        assert api.post(f"/v1/runs/{run_id}/feedback", json={"satisfactory": ok, "reason": reason}).status_code == 201
    s = api.get("/v1/feedback/summary").json()
    assert s["overall"] == {"total": 4, "satisfactory": 2, "rate": 0.5}
    assert sum(v["total"] for v in s["by_route"].values()) == 4
    assert s["by_day"][0]["total"] == 4
    top = {r["reason"]: r for r in s["top_reasons"]}
    assert top["missed the veg mark"] == {"reason": "missed the veg mark", "count": 2, "unsatisfactory": 2}


def test_empty_summary(api):
    s = api.get("/v1/feedback/summary", params={"days": 7}).json()
    assert s["overall"] == {"total": 0, "satisfactory": 0, "rate": None} and s["days"] == 7


def test_routes_are_auto_mounted(api):
    assert {"feedback", "quarantine"} <= set(api.app.state.routers)
    paths = set(api.get("/openapi.json").json()["paths"])
    assert {"/v1/quarantine", "/v1/quarantine/{quarantine_id}", "/v1/runs/{run_id}/feedback",
            "/v1/feedback/summary"} <= paths


def test_stores_down_give_honest_errors_not_500s(api):
    class Down:
        def since(self, start):
            raise ConnectionError("postgres down")

        def add(self, rec):
            raise ConnectionError("postgres down")

    api.app.state.feedback_store = Down()
    run_id = finished_run(api)
    assert api.post(f"/v1/runs/{run_id}/feedback", json={"satisfactory": True, "reason": "x"}).status_code == 503
    assert api.get("/v1/feedback/summary").status_code == 503
