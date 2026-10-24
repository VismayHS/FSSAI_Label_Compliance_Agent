"""The verifier and router keep their seams' contracts (fssai_contracts.conformance).

Day-0 baseline: each skeleton raises NotImplementedError, so these are expected failures until the task is
built. strict=True turns the first pass into a failure that reminds you to delete that marker. Your own
behaviour tests go in other files next to this one.
"""
import pytest

from fssai_contracts.conformance import check_router, check_verifier
from fssai_verification.router import RuleRouter
from fssai_verification.verifier import AgentVerifier


def pending(task):
    return pytest.mark.xfail(raises=NotImplementedError, strict=True,
                             reason=f"{task} not built yet: delete this marker when it passes")


@pending("V2.1")
def test_verifier_conforms():
    check_verifier(AgentVerifier.from_registry())


@pending("V2.2")
def test_router_conforms():
    check_router(RuleRouter())
