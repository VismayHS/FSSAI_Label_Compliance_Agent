"""RequestGate keeps the gate contract (fssai_contracts.conformance.check_gate).

Built (V1.2), so the day-0 xfail marker is gone and this guards the contract. Behaviour tests are in
test_rules.py, test_gate.py and test_gate_properties.py.
"""
from fssai_contracts.conformance import check_gate
from fssai_gate.gate import RequestGate


def test_conforms():
    check_gate(RequestGate())


def test_conforms_as_built_from_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("QUARANTINE_STORE", "memory")
    check_gate(RequestGate.from_registry())
