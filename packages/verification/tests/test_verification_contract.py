"""The verifier and router keep their seams' contracts (fssai_contracts.conformance).

Built (V2.1, V2.2), so the day-0 xfail markers are gone: these now guard the contract. Behaviour tests are in
test_verifier.py, test_checks.py and test_router.py.
"""
from fssai_contracts.conformance import check_router, check_verifier
from fssai_verification.router import RuleRouter
from fssai_verification.verifier import AgentVerifier


def test_verifier_conforms():
    check_verifier(AgentVerifier.from_registry())


def test_router_conforms():
    check_router(RuleRouter())
