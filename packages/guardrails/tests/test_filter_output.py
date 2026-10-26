"""Output filtering (M3.1): never approve, never upgrade, only cite what was retrieved."""
import itertools

import pytest

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    NOT_AN_APPROVAL, Citation, Finding, FindingStatus, Regulation, Route, Routing, RunResult, Verdict, VerifyAction,
)
from fssai_guardrails.guardrails import REDACTED, TOXIC_REDACTED, Guardrails

PASSAGE_TEXT = "A claim that a food is a source of protein may be made only where it provides 10% of RDA per 100 g."
QUOTE = "may be made only where it provides 10% of RDA per 100 g"
SEVERITY = {Route.CLEAR_FOR_PRINT: 0, Route.REVISE_AND_RECHECK: 1, Route.REGULATORY_REVIEW: 2}


def ctx_with_passage(pid="AC:5(3)", text=PASSAGE_TEXT) -> RunContext:
    ctx = RunContext.new()
    ctx.record(agent="researcher", kind="tool", name="corpus_search",
               output={"passages": [{"passage_id": pid, "regulation": "FSS-AC-2018", "clause_id": "5(3)", "text": text}]})
    return ctx


def finding(status=FindingStatus.MET, pid="AC:5(3)", quote=QUOTE, rid="CLM-PROTEIN-SOURCE", explanation="ok"):
    cites = [Citation(regulation=Regulation.CLAIMS_2018, clause_id="5(3)", passage_id=pid, quote=quote)] if quote else []
    return Finding(requirement_id=rid, requirement="Protein claim condition", status=status,
                   explanation=explanation, citations=cites)


def result(route=Route.CLEAR_FOR_PRINT, *, complete=True, verdict_action=VerifyAction.ACCEPT, findings=None,
           reason="All checked requirements met, citations verified.", ctx=None, **kw):
    ctx = ctx or RunContext.new()
    verdict = Verdict(action=verdict_action) if verdict_action else None
    return RunResult(run_id=ctx.run_id, correlation_id=ctx.correlation_id, complete=complete,
                     routing=Routing(route=route, reason=reason), verdict=verdict,
                     findings=[finding()] if findings is None else findings, **kw)


def run(res, ctx=None):
    ctx = ctx or ctx_with_passage()
    return Guardrails().filter_output(res, ctx), ctx


# ---------------------------------------------------------------- a clean, supported result passes untouched

def test_a_supported_accepted_clear_result_stays_clear():
    out, _ = run(result())
    assert out.routing.route == Route.CLEAR_FOR_PRINT
    assert out.guardrails[-1].stage == "output" and out.guardrails[-1].allowed and not out.guardrails[-1].flags
    assert out.findings[0].citations and out.notice == NOT_AN_APPROVAL


def test_the_hyphenated_route_name_is_not_treated_as_approval_wording():
    out, _ = run(result(reason="Routed to clear-for-print: all requirements met."))
    assert "clear-for-print" in out.routing.reason and REDACTED not in out.routing.reason


# ---------------------------------------------------------------- forced downgrades

@pytest.mark.parametrize("kwargs", [
    {"verdict_action": None},
    {"verdict_action": VerifyAction.ESCALATE},
    {"verdict_action": VerifyAction.RETRY},
    {"complete": False},
    {"findings": []},
    {"findings": [finding(FindingStatus.UNMET)]},
    {"findings": [finding(FindingStatus.CANNOT_DETERMINE)]},
    {"findings": [finding(FindingStatus.MET, quote=None)]},
], ids=["no-verdict", "escalate", "retry", "incomplete", "no-findings", "unmet", "undetermined", "uncited"])
def test_clear_for_print_is_forced_to_regulatory_review(kwargs):
    out, _ = run(result(**kwargs))
    assert out.routing.route == Route.REGULATORY_REVIEW
    assert out.routing.reason.startswith("Escalated by the output guardrail")
    assert any(f.startswith("route_downgraded:clear-for-print") for f in out.guardrails[-1].flags)


def test_revise_and_recheck_on_an_unverified_or_incomplete_run_goes_to_review():
    for kwargs in ({"verdict_action": VerifyAction.ESCALATE}, {"complete": False}):
        out, _ = run(result(Route.REVISE_AND_RECHECK, findings=[finding(FindingStatus.UNMET)], **kwargs))
        assert out.routing.route == Route.REGULATORY_REVIEW


def test_a_supported_revise_result_stays_revise():
    out, _ = run(result(Route.REVISE_AND_RECHECK, findings=[finding(FindingStatus.UNMET)]))
    assert out.routing.route == Route.REVISE_AND_RECHECK


def test_regulatory_review_is_never_changed():
    out, _ = run(result(Route.REGULATORY_REVIEW, verdict_action=VerifyAction.ACCEPT))
    assert out.routing.route == Route.REGULATORY_REVIEW


def test_no_combination_of_inputs_ever_upgrades_a_route():
    for route, action, complete, status, cited in itertools.product(
            Route, [None, *VerifyAction], [True, False], FindingStatus, [True, False]):
        res = result(route, verdict_action=action, complete=complete,
                     findings=[finding(status, quote=QUOTE if cited else None)])
        out, _ = run(res)
        assert SEVERITY[out.routing.route] >= SEVERITY[route], (route, action, complete, status, cited)
        assert out.notice == NOT_AN_APPROVAL and out.guardrails[-1].stage == "output"
        if out.routing.route == Route.CLEAR_FOR_PRINT:
            assert action == VerifyAction.ACCEPT and complete and status in (FindingStatus.MET, FindingStatus.NOT_APPLICABLE)
            assert status == FindingStatus.NOT_APPLICABLE or cited


# ---------------------------------------------------------------- approval wording

@pytest.mark.parametrize("text", [
    "This label is approved for print.", "Approval granted.", "The packaging has been approved.",
    "I hereby approve this artwork.", "Safe to print.", "Ready to print", "You may now print it.",
    "The label is fully compliant.", "It complies with all FSSAI requirements.",
])
def test_approval_wording_is_removed_everywhere_it_can_appear(text):
    res = result(Route.REVISE_AND_RECHECK, findings=[finding(FindingStatus.UNMET, explanation=text)], reason=text)
    out, _ = run(res)
    assert REDACTED in out.routing.reason and REDACTED in out.findings[0].explanation
    assert any(f.startswith("approval_wording:") for f in out.guardrails[-1].flags)
    assert not out.guardrails[-1].allowed


def test_approval_wording_in_the_verdict_reason_is_removed():
    res = result(Route.REGULATORY_REVIEW)
    res = res.model_copy(update={"verdict": Verdict(action=VerifyAction.ESCALATE, escalation_reason="Label approved for print")})
    out, _ = run(res)
    assert REDACTED in out.verdict.escalation_reason


def test_the_not_an_approval_notice_is_restored_if_it_was_changed():
    res = result().model_copy(update={"notice": "Approved."})
    out, _ = run(res)
    assert out.notice == NOT_AN_APPROVAL


# ---------------------------------------------------------------- citations must come from this run

def test_a_citation_to_a_passage_not_in_the_trace_is_removed_and_the_route_downgraded():
    out, _ = run(result(findings=[finding(pid="made-up")]))
    f = out.findings[0]
    assert not f.citations and f.status == FindingStatus.CANNOT_DETERMINE
    assert out.routing.route == Route.REGULATORY_REVIEW
    assert "citation_removed:CLM-PROTEIN-SOURCE" in out.guardrails[-1].flags


def test_a_quote_that_is_not_verbatim_is_removed():
    out, _ = run(result(Route.REVISE_AND_RECHECK, findings=[finding(FindingStatus.UNMET, quote="needs thirty percent protein")]))
    assert not out.findings[0].citations and out.findings[0].status == FindingStatus.CANNOT_DETERMINE


def test_one_good_citation_survives_when_another_is_removed():
    f = finding()
    f = f.model_copy(update={"citations": [*f.citations, Citation(regulation=Regulation.CLAIMS_2018, clause_id="x",
                                                                    passage_id="made-up", quote="nothing")]})
    out, _ = run(result(Route.REVISE_AND_RECHECK, findings=[f]))
    assert len(out.findings[0].citations) == 1 and out.findings[0].status == FindingStatus.MET


def test_passages_in_the_result_trace_count_as_retrieved():
    ctx = RunContext.new()
    traced = ctx_with_passage()
    res = result(ctx=ctx).model_copy(update={"steps": list(traced.steps)})
    out = Guardrails().filter_output(res, ctx)
    assert out.findings[0].citations and out.routing.route == Route.CLEAR_FOR_PRINT


# ---------------------------------------------------------------- toxicity and bookkeeping

def test_toxic_output_text_is_redacted():
    res = result(Route.REVISE_AND_RECHECK, findings=[finding(FindingStatus.UNMET, explanation="this is bullshit")])
    out, _ = run(res)
    assert out.findings[0].explanation == TOXIC_REDACTED
    assert any(f.startswith("toxicity:") for f in out.guardrails[-1].flags)


def test_the_filter_records_one_step_and_appends_one_report():
    out, ctx = run(result())
    assert [s.name for s in ctx.steps if s.kind == "guardrail"] == ["filter_output"]
    assert len(out.guardrails) == 1


def test_earlier_reports_are_kept():
    first = Guardrails().screen_input(__import__("fssai_contracts.conformance", fromlist=["x"]).sample_request(), RunContext.new())
    out, _ = run(result(guardrails=[first]))
    assert [g.stage for g in out.guardrails] == ["input", "output"]
