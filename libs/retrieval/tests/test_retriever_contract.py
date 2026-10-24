"""FaissRetriever keeps the retriever contract (fssai_contracts.conformance.check_retriever).

Day-0 baseline: the skeleton raises NotImplementedError, so this is an expected failure until N2.2
is built. strict=True turns the first pass into a failure that reminds you to delete the marker;
from then on it guards the contract. Your own behaviour tests go in other files next to this one.
"""
import pytest

from fssai_contracts.conformance import check_retriever
from fssai_retrieval.faiss_retriever import FaissRetriever


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="N2.2 not built yet: delete this marker when it passes")
def test_conforms():
    check_retriever(FaissRetriever.from_registry())
