"""The real guardrails inside the reference pipeline (everything else is a fake): demo item 7 end to end."""
from fssai_contracts.conformance import INJECTION, sample_request
from fssai_contracts.context import RunContext
from fssai_contracts.fakes import FakeClassifier, FakeResearcher, FakeRouter, FakeVerifier
from fssai_contracts.pipeline import ReferencePipeline
from fssai_contracts.schemas import Route
from fssai_guardrails.guardrails import Guardrails


def pipeline():
    return ReferencePipeline(guardrails=Guardrails(), classifier=FakeClassifier(), researcher=FakeResearcher(),
                             verifier=FakeVerifier(), router=FakeRouter())


def test_injection_stops_the_run_before_any_agent_and_says_why():
    ctx = RunContext.new()
    r = pipeline().run(sample_request(front_of_pack_text=INJECTION), ctx)
    assert r.routing.route == Route.REGULATORY_REVIEW and r.complete
    assert "prompt_injection:label.front_of_pack_text" in r.routing.escalation_reason
    assert r.classification is None and not any(s.kind in ("classification", "tool", "llm") for s in r.steps)
    assert r.guardrails[0].stage == "input" and r.guardrails[-1].stage == "output"


def test_a_clean_request_still_flows_through_and_is_cleared_only_with_support():
    ctx = RunContext.new()
    r = pipeline().run(sample_request(), ctx)
    assert r.complete and r.guardrails[0].allowed
    assert r.routing.route in (Route.CLEAR_FOR_PRINT, Route.REVISE_AND_RECHECK, Route.REGULATORY_REVIEW)
    for f in r.findings:
        for c in f.citations:
            assert any(c.passage_id == p["passage_id"] for s in r.steps if s.kind == "tool" for p in s.output["passages"])
