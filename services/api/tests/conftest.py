from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from fssai_contracts.fakes import FakeRequestGate, InMemoryRunStore
from fssai_contracts.pipeline import ReferencePipeline
from fssai_worker.jobs import Deps, execute_run

from app.main import create_app

# §4.1-shaped request on the fakes: the fake claim condition is 10 g protein per 100 g (PLACEHOLDER).
SECTION_41 = {
    "declared_category": "demo-category",
    "package": {"net_quantity": 200, "net_quantity_unit": "g", "principal_display_panel_cm2": 120},
    "label": {"product_name": "Roasted chana", "brand_name": "Kurkure Fields", "claims": ["Source of protein"],
              "front_of_pack_text": "Source of protein. Roasted, not fried.", "ingredients": "Bengal gram, salt",
              "allergen_statement": "Contains: chickpea", "veg_status": "veg"},
    "nutrition": {"basis": "per_100g", "energy_kcal": 380, "protein_g": 12, "carbohydrate_g": 55,
                  "total_sugars_g": 3, "total_fat_g": 6},
}


def section_41(**nutrition) -> dict:
    body = copy.deepcopy(SECTION_41)
    body["nutrition"].update(nutrition)
    return body


class SyncDispatcher:
    """Runs the job before the POST returns, so tests can assert on the finished run."""

    mode = "inline"

    def __init__(self, deps: Deps) -> None:
        self.deps, self.submitted = deps, []

    def submit(self, payload):
        self.submitted.append(payload)
        execute_run(payload, self.deps)

    def ready(self):
        return True, "test"


class Env:
    def __init__(self, dispatcher=None, gate=None) -> None:
        self.store = InMemoryRunStore()
        self.gate = gate or FakeRequestGate()
        self.dispatcher = dispatcher or SyncDispatcher(Deps(pipeline=ReferencePipeline.from_registry(),
                                                            run_store=self.store))
        self.app = create_app(gate=self.gate, run_store=self.store, dispatcher=self.dispatcher)
        self.client = TestClient(self.app)

    def submit(self, body=None, *, client_id="analyst-1", **headers):
        hdrs = {"X-Client-Id": client_id, **headers} if client_id else headers
        return self.client.post("/v1/runs", json=SECTION_41 if body is None else body, headers=hdrs)


@pytest.fixture
def env() -> Env:
    return Env()
