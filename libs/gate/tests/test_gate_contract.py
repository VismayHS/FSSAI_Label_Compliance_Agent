"""RequestGate keeps the gate contract (fssai_contracts.conformance.check_gate).

Day-0 baseline: the skeleton raises NotImplementedError, so this is an expected failure until V1.2
is built. strict=True turns the first pass into a failure that reminds you to delete the marker;
from then on it guards the contract. Your own behaviour tests go in other files next to this one.
"""
import pytest

from fssai_contracts.conformance import check_gate
from fssai_gate.gate import RequestGate


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="V1.2 not built yet: delete this marker when it passes")
def test_conforms():
    check_gate(RequestGate())
