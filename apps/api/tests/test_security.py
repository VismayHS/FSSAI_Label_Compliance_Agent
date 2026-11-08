"""API security (docs/security.md): keys, object- and function-level authorisation, headers, safe errors."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fssai_contracts.fakes import FakeRequestGate, InMemoryRunStore
from fssai_contracts.pipeline import ReferencePipeline
from fssai_worker.jobs import Deps

from app.main import Settings, create_app
from app.security import KeyRing, hash_key

from .conftest import SECTION_41, SyncDispatcher

ALICE, BOB, LEAD = "key-alice-0123456789", "key-bob-0123456789", "key-lead-0123456789"
RING = f"alice:{hash_key(ALICE)},bob:{hash_key(BOB)}:analyst,lead:{hash_key(LEAD)}:reviewer"


def make(ring: str = RING, **settings) -> TestClient:
    store = InMemoryRunStore()
    app = create_app(gate=FakeRequestGate(), run_store=store, keyring=KeyRing.parse(ring),
                     settings=Settings(**settings),
                     dispatcher=SyncDispatcher(Deps(pipeline=ReferencePipeline.from_registry(), run_store=store)))
    return TestClient(app)


@pytest.fixture
def api() -> TestClient:
    return make()


def submit(api: TestClient, key: str | None, **headers):
    if key:
        headers["X-API-Key"] = key
    return api.post("/v1/runs", json=SECTION_41, headers=headers)


# ---------------------------------------------------------------- authentication (API2)

def test_no_key_is_refused_with_401_and_no_run_starts(api):
    r = submit(api, None, **{"X-Client-Id": "alice"})
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("ApiKey")
    assert r.json()["correlation_id"]
    assert api.app.state.run_store.recent(10) == []


def test_a_wrong_key_is_refused(api):
    assert submit(api, "not-a-key").status_code == 401
    assert api.get("/v1/runs", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_a_valid_key_works_in_either_header(api):
    assert submit(api, ALICE).status_code == 202
    assert api.get("/v1/runs", headers={"Authorization": f"Bearer {ALICE}"}).status_code == 200


def test_health_metrics_and_contract_stay_public(api):
    for path in ("/healthz", "/readyz", "/metrics", "/openapi.json"):
        assert api.get(path).status_code == 200, path


def test_the_key_never_appears_in_responses_or_logs(api, caplog):
    caplog.set_level("INFO")
    submit(api, ALICE)
    r = submit(api, "wrong-key-value-123")
    assert "wrong-key-value-123" not in r.text and "wrong-key-value-123" not in caplog.text
    assert ALICE not in caplog.text


# ---------------------------------------------------------------- client id bound to the key (API4)

def test_client_id_comes_from_the_key_not_the_header(api):
    run_id = submit(api, ALICE, **{"X-Client-Id": "someone-else"}).json()["run_id"]
    assert api.app.state.run_store.get(run_id).client_id == "alice"


def test_submitting_without_x_client_id_is_fine_when_keys_are_on(api):
    assert submit(api, BOB).status_code == 202


# ---------------------------------------------------------------- object-level authorisation (API1)

def test_another_analysts_run_is_not_found(api):
    run_id = submit(api, ALICE).json()["run_id"]
    for suffix in ("", "/trace", "/events"):
        r = api.get(f"/v1/runs/{run_id}{suffix}", headers={"X-API-Key": BOB})
        assert r.status_code == 404, suffix
        assert r.json()["detail"] == "No run with this id."  # same as an unknown id: ids can't be probed
    assert api.get(f"/v1/runs/{run_id}", headers={"X-API-Key": ALICE}).status_code == 200


def test_listing_shows_an_analyst_only_their_own_runs(api):
    mine = submit(api, ALICE).json()["run_id"]
    theirs = submit(api, BOB).json()["run_id"]
    alice = {r["run_id"] for r in api.get("/v1/runs", headers={"X-API-Key": ALICE}).json()}
    lead = {r["run_id"] for r in api.get("/v1/runs", headers={"X-API-Key": LEAD}).json()}
    assert alice == {mine}
    assert lead == {mine, theirs}


def test_a_reviewer_reads_any_run(api):
    run_id = submit(api, ALICE).json()["run_id"]
    assert api.get(f"/v1/runs/{run_id}/trace", headers={"X-API-Key": LEAD}).status_code == 200


# ---------------------------------------------------------------- function-level authorisation (API5)

def test_quarantine_is_reviewer_only(api):
    assert api.get("/v1/quarantine", headers={"X-API-Key": ALICE}).status_code == 403
    assert api.get("/v1/quarantine", headers={"X-API-Key": LEAD}).status_code == 200


# ---------------------------------------------------------------- headers, errors, docs (API8)

def test_security_headers_on_api_responses(api):
    r = submit(api, ALICE)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert r.headers["Cache-Control"] == "no-store"
    assert "X-Correlation-Id" in r.headers


def test_unexpected_errors_never_leak_a_stack_trace():
    api = make("")

    @api.app.get("/v1/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    r = TestClient(api.app, raise_server_exceptions=False).get("/v1/boom")
    assert r.status_code == 500
    assert "secret internal detail" not in r.text and "Traceback" not in r.text
    assert r.json()["detail"].startswith("Internal error")


def test_docs_can_be_switched_off_but_the_contract_stays():
    api = make(docs_enabled=False)
    assert api.get("/docs").status_code == 404
    assert api.get("/openapi.json").status_code == 200


def test_openapi_publishes_the_key_scheme(api):
    spec = api.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["ApiKey"]["name"] == "X-API-Key"
    assert spec["paths"]["/v1/runs"]["post"]["security"] == [{"ApiKey": []}]


# ---------------------------------------------------------------- configuration

def test_without_keys_the_api_stays_open_as_in_a_clean_clone():
    api = make("")
    assert api.post("/v1/runs", json=SECTION_41, headers={"X-Client-Id": "analyst-1"}).status_code == 202


@pytest.mark.parametrize("bad", [
    "alice",                                   # no hash
    f"alice:{ALICE}",                          # a plain-text key instead of its hash
    f"al ice:{hash_key(ALICE)}",               # bad client id
    f"alice:{hash_key(ALICE)}:admin",          # unknown role
])
def test_a_malformed_key_ring_fails_at_start_up(bad):
    with pytest.raises(ValueError):
        KeyRing.parse(bad)
