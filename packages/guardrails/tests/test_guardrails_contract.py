"""Guardrails keeps the guardrails contract (fssai_contracts.conformance.check_guardrails).

Day-0 baseline: the skeleton raises NotImplementedError, so this is an expected failure until M3.1
is built. strict=True turns the first pass into a failure that reminds you to delete the marker;
from then on it guards the contract. Your own behaviour tests go in other files next to this one.
"""
from fssai_contracts.conformance import check_guardrails
from fssai_guardrails.guardrails import Guardrails


def test_conforms():
    check_guardrails(Guardrails())
