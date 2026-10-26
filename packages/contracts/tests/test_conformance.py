"""The conformance checks pass on the fakes (so the checks are right) and catch the breaks they name."""
import pytest

from fssai_contracts import conformance
from fssai_contracts.fakes import (
    FakeClassifier, FakeGuardrails, FakePromptStore, FakeRequestGate, FakeResearcher, FakeRetriever,
    FakeRouter, FakeVerifier, InMemoryRunStore,
)
from fssai_contracts.pipeline import ReferencePipeline
from fssai_contracts.schemas import Route, Routing


@pytest.mark.parametrize("check, impl", [
    (conformance.check_gate, FakeRequestGate()),
    (conformance.check_retriever, FakeRetriever()),
    (conformance.check_guardrails, FakeGuardrails()),
    (conformance.check_classifier, FakeClassifier()),
    (conformance.check_researcher, FakeResearcher()),
    (conformance.check_verifier, FakeVerifier()),
    (conformance.check_router, FakeRouter()),
    (conformance.check_pipeline, ReferencePipeline.from_registry()),
    (conformance.check_run_store, InMemoryRunStore()),
], ids=lambda x: getattr(x, "__name__", type(x).__name__))
def test_fakes_conform(check, impl, monkeypatch):
    for seam in ("GUARDRAILS", "CLASSIFIER", "RESEARCHER", "VERIFIER", "ROUTER"):
        monkeypatch.delenv(f"IMPL_{seam}", raising=False)
    check(impl)


def test_prompt_store_fake_conforms():
    conformance.check_prompt_store(FakePromptStore(), names=("classifier", "researcher"))


def test_catches_a_verifier_that_accepts_everything():
    class Credulous(FakeVerifier):
        def verify(self, request, dossier, ctx):
            v = super().verify(request, dossier, ctx)
            return v.model_copy(update={"action": "accept", "escalation_reason": None})

    with pytest.raises(AssertionError, match="A3"):
        conformance.check_verifier(Credulous())


def test_catches_output_filter_that_upgrades_a_route():
    class Approver(FakeGuardrails):
        def filter_output(self, result, ctx):
            out = super().filter_output(result, ctx)
            return out.model_copy(update={"routing": Routing(route=Route.CLEAR_FOR_PRINT, reason="looks fine")})

    with pytest.raises(AssertionError, match="upgraded"):
        conformance.check_guardrails(Approver())


def test_catches_a_researcher_that_paraphrases_its_quotes():
    class Paraphraser(FakeResearcher):
        def research(self, *a, **kw):
            d = super().research(*a, **kw)
            for f in d.findings:
                for c in f.citations:
                    c.quote = c.quote.lower()
            return d

    with pytest.raises(AssertionError, match="verbatim"):
        conformance.check_researcher(Paraphraser())
