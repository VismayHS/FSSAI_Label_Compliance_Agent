"""Behaviour tests for the guardrails (M3.1, L4): the red-team fixtures, clean labels, and the output filter."""
from pathlib import Path

import pytest
import yaml

from fssai_contracts.conformance import sample_request
from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    Citation, Finding, FindingStatus, Route, Routing, RunResult, Verdict, VerifyAction,
)
from fssai_guardrails.guardrails import REDACTED_APPROVAL, Guardrails

ATTACKS = yaml.safe_load((Path(__file__).parent / "attacks.yaml").read_text(encoding="utf-8"))
G = Guardrails()


def with_text(field: str, text: str):
    if field == "claims":
        return sample_request(claims=(text,))
    return sample_request(**{field: text})


def test_fixture_has_enough_attacks_in_every_field():
    assert len(ATTACKS) >= 15
    assert {a["field"] for a in ATTACKS} >= {"claims", "front_of_pack_text", "ingredients", "other_text"}
    assert len({a["id"] for a in ATTACKS}) == len(ATTACKS)


@pytest.mark.parametrize("attack", ATTACKS, ids=[a["id"] for a in ATTACKS])
def test_each_attack_is_flagged_and_blocks_the_run(attack):
    report = G.screen_input(with_text(attack["field"], attack["text"]), RunContext.new())
    assert not report.allowed, f"not detected: {attack['text']!r}"
    assert any(f.startswith(("prompt_injection", "control_characters")) for f in report.flags)


def test_a_clean_label_passes():
    report = G.screen_input(sample_request(), RunContext.new())
    assert report.allowed and report.flags == []


@pytest.mark.parametrize("text", [
    "Source of protein", "High in fibre", "Made with whole grain oats", "No added sugar",
    "Store in a cool dry place. Best before 9 months from manufacture.",
    "Contains wheat and milk. May contain traces of nuts.",
])
def test_ordinary_label_wording_is_not_flagged(text):
    assert G.screen_input(sample_request(front_of_pack_text=text), RunContext.new()).allowed


def test_over_long_field_is_flagged(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_MAX_FIELD_CHARS", "50")
    report = G.screen_input(sample_request(other_text="x" * 51), RunContext.new())
    assert not report.allowed and any(f.startswith("too_long:") for f in report.flags)


def test_control_and_bidi_characters_are_flagged():
    report = G.screen_input(sample_request(other_text="Price ‮evil‬ \x07"), RunContext.new())
    assert any(f.startswith("control_characters:") for f in report.flags)


def test_screening_is_recorded_in_the_trace():
    ctx = RunContext.new()
    G.screen_input(sample_request(), ctx)
    assert any(s.kind == "guardrail" and s.name == "screen_input" for s in ctx.steps)


# --------------------------------------------------------------------------- output filter

def result(route=Route.CLEAR_FOR_PRINT, action=VerifyAction.ACCEPT, status=FindingStatus.MET,
           reason="All requirements met.", complete=True, citations=()) -> RunResult:
    from fssai_contracts.fakes import FakeRouter  # noqa: F401  (keeps the import path honest)
    finding = Finding(requirement_id="R1", requirement="Declare protein", status=status,
                      explanation="Protein is declared.", citations=list(citations))
    return RunResult.model_validate({
        **_base_result(), "routing": Routing(route=route, reason=reason), "findings": [finding],
        "verdict": Verdict(action=action, reason="checked"), "complete": complete})


def _base_result() -> dict:
    from fssai_contracts.pipeline import ReferencePipeline
    from fssai_contracts.registry import build
    ctx = RunContext.new()
    base = ReferencePipeline.from_registry().run(sample_request(), ctx)
    return {k: v for k, v in base.model_dump().items() if k not in ("routing", "findings", "verdict", "complete")}


def test_approval_wording_is_redacted_and_route_never_upgraded():
    out = G.filter_output(result(route=Route.REVISE_AND_RECHECK, reason="The label is approved for print."), RunContext.new())
    assert "approved for print" not in out.routing.reason.lower()
    assert REDACTED_APPROVAL in out.routing.reason
    assert out.routing.route == Route.REVISE_AND_RECHECK


def test_negated_approval_wording_is_left_alone():
    out = G.filter_output(result(route=Route.REGULATORY_REVIEW, reason="This system cannot say the label is approved."),
                          RunContext.new())
    assert "cannot say the label is approved" in out.routing.reason


def test_clear_for_print_without_accept_is_forced_to_review():
    out = G.filter_output(result(action=VerifyAction.RETRY), RunContext.new())
    assert out.routing.route == Route.REGULATORY_REVIEW and out.routing.escalation_reason


def test_clear_for_print_with_a_failed_finding_is_forced_to_review():
    out = G.filter_output(result(status=FindingStatus.UNMET), RunContext.new())
    assert out.routing.route == Route.REGULATORY_REVIEW


def test_incomplete_run_is_forced_to_review():
    out = G.filter_output(result(complete=False), RunContext.new())
    assert out.routing.route == Route.REGULATORY_REVIEW


def test_citation_not_in_the_trace_is_removed_and_finding_downgraded():
    cite = Citation(regulation="FSS-AC-2018", clause_id="x", passage_id="p-missing", quote="invented text")
    out = G.filter_output(result(route=Route.REVISE_AND_RECHECK, citations=[cite]), RunContext.new())
    assert out.findings[0].citations == []
    assert out.findings[0].status == FindingStatus.CANNOT_DETERMINE
    assert any(f.startswith("unresolved_citation_removed") for f in out.guardrails[-1].flags)


def test_the_not_an_approval_notice_is_always_present_and_filtering_is_recorded():
    ctx = RunContext.new()
    out = G.filter_output(result(), ctx)
    assert out.notice
    assert any(s.kind == "guardrail" and s.name == "filter_output" for s in ctx.steps)
