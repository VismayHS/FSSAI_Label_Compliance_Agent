"""FilePromptStore keeps the prompt store contract (fssai_contracts.conformance.check_prompt_store).

Day-0 baseline: the skeleton raises NotImplementedError, so this is an expected failure until M1.1
is built. strict=True turns the first pass into a failure that reminds you to delete the marker;
from then on it guards the contract. Your own behaviour tests go in other files next to this one.
"""
import pytest

from fssai_contracts.conformance import check_prompt_store
from fssai_prompts.store import FilePromptStore


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="M1.1 not built yet: delete this marker when it passes")
def test_conforms():
    check_prompt_store(FilePromptStore(), names=("classifier", "researcher"))
