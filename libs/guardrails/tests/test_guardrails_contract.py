"""Guardrails keeps the guardrails contract (fssai_contracts.conformance.check_guardrails).

"""
from fssai_contracts.conformance import check_guardrails
from fssai_guardrails.guardrails import Guardrails


def test_conforms():
    check_guardrails(Guardrails())
