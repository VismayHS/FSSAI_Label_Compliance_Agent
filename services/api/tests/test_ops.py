"""Health, readiness, metrics, router auto-mounting and the published OpenAPI contract."""
from __future__ import annotations

import pkgutil

from fastapi.testclient import TestClient

from fssai_contracts.fakes import InMemoryRunStore

from app import routers
from app.main import create_app

from .conftest import Env


def test_healthz(env):
    assert env.client.get("/healthz").json() == {"status": "ok"}


def test_readyz_ok_in_inline_mode(env):
    r = env.client.get("/readyz")
    assert r.status_code == 200 and r.json()["ready"] is True


def test_readyz_refuses_queue_mode_with_an_in_memory_store():
    class Queue:
        mode = "queue"

        def submit(self, payload):
            pass

        def ready(self):
            return True, "reachable"

    r = Env(dispatcher=Queue()).client.get("/readyz")
    assert r.status_code == 503
    assert "shared run store" in r.json()["checks"]["run_store"]["detail"]


def test_readyz_reports_an_unreachable_queue():
    class Down:
        mode = "queue"

        def submit(self, payload):
            pass

        def ready(self):
            return False, "queue unreachable: ConnectionError"

    class SharedStore(InMemoryRunStore):
        pass

    env = Env(dispatcher=Down())
    env.app.state.run_store = SharedStore()
    r = env.client.get("/readyz")
    assert r.status_code == 503 and r.json()["checks"]["dispatch"]["ok"] is False


def test_metrics_expose_http_and_run_counters(env):
    env.submit()
    text = env.client.get("/metrics").text
    assert "fssai_http_requests_total" in text and 'fssai_runs_submitted_total{outcome="accepted"}' in text
    assert "fssai_runs_finished_total" in text


def test_every_router_module_is_mounted(env):
    # Teammates' routers (feedback, quarantine) are picked up without editing main.py, so compare with the package.
    modules = sorted(m.name for m in pkgutil.iter_modules(routers.__path__))
    assert env.app.state.routers == modules and {"health", "runs"} <= set(modules)


def test_openapi_publishes_the_request_contract(env):
    spec = env.client.get("/openapi.json").json()
    body = spec["paths"]["/v1/runs"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/LabelCheckRequest"}
    assert "LabelCheckRequest" in spec["components"]["schemas"]
    assert {"202", "400", "413", "422", "429", "503"} <= set(spec["paths"]["/v1/runs"]["post"]["responses"])


def test_create_app_builds_its_dependencies_from_the_registry(monkeypatch):
    monkeypatch.delenv("RUN_DISPATCH", raising=False)
    app = create_app()
    assert app.state.dispatcher.mode == "inline"
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200


def test_readyz_says_which_parts_are_stand_ins(env, monkeypatch):
    for seam in ("CLASSIFIER", "RETRIEVER"):
        monkeypatch.delenv(f"IMPL_{seam}", raising=False)
    monkeypatch.setenv("IMPL_RETRIEVER", "fssai_retrieval.faiss_retriever:FaissRetriever   # real")
    parts = env.client.get("/readyz").json()["components"]
    assert parts["classifier"] == {"impl": "fssai_contracts.fakes:FakeClassifier", "stand_in": True}
    assert parts["retriever"] == {"impl": "fssai_retrieval.faiss_retriever:FaissRetriever", "stand_in": False}
    assert set(parts) >= {"gate", "llm", "researcher", "verifier", "router", "guardrails", "pipeline", "run_store"}
