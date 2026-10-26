"""RuleRouter: one test per rule in docs/decisions/201-vihaan-routing-rules.md."""
import pytest

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import NOT_AN_APPROVAL, Classification, FindingStatus, Route, Verdict, VerifyAction
from fssai_verification.router import RuleRouter, decide

from verification_helpers import SCHED, cite, dossier, finding, request

MET, UNMET, NA, CD = FindingStatus.MET, FindingStatus.UNMET, FindingStatus.NOT_APPLICABLE, FindingStatus.CANNOT_DETERMINE
ACCEPT = Verdict(action=VerifyAction.ACCEPT)
IN_SCOPE = Classification(category="breakfast-cereals", in_scope=True)


def lbl(rid="LBL-ALLERGEN", status=MET, explanation=""):
    return finding(rid, status, cite(SCHED["allergen"]), explanation=explanation)


def clm(status=MET):
    return finding("CLM-FIBRE-SOURCE", status, cite(SCHED["fibre"]))


def rule(d, verdict=ACCEPT, classification=IN_SCOPE, claims=()):
    return decide(request(claims), classification, d, verdict)


@pytest.mark.parametrize("action", [VerifyAction.RETRY, VerifyAction.ESCALATE])
def test_r1_unverified(action):
    r, routing = rule(dossier(lbl()), Verdict(action=action, escalation_reason="quote not verbatim"))
    assert r == "R1" and routing.route == Route.REGULATORY_REVIEW and "quote not verbatim" in routing.escalation_reason


def test_r1_without_a_reason_still_gives_one():
    _, routing = rule(dossier(lbl()), Verdict(action=VerifyAction.RETRY))
    assert routing.escalation_reason


def test_r2_out_of_scope():
    r, routing = rule(dossier(lbl()), classification=Classification(category="alcoholic-beverage", in_scope=False))
    assert r == "R2" and "alcoholic-beverage" in routing.escalation_reason


def test_r3_signals():
    r, routing = rule(dossier(lbl(), signals=("8(1) may exempt this pack",)))
    assert r == "R3" and "8(1)" in routing.reason


def test_r4_no_findings():
    r, routing = rule(dossier())
    assert r == "R4" and routing.route == Route.REGULATORY_REVIEW


def test_r5_undetermined_also_lists_what_to_fix():
    r, routing = rule(dossier(lbl("LBL-VEG-MARK", UNMET, "No veg logo."), clm(CD)), claims=("Source of fibre",))
    assert r == "R5" and routing.route == Route.REGULATORY_REVIEW
    assert "CLM-FIBRE-SOURCE" in routing.escalation_reason and "LBL-VEG-MARK (No veg logo.)" in routing.reason


def test_r6_claim_never_checked_against_the_claims_regulation():
    r, routing = rule(dossier(lbl()), claims=("Source of fibre",))
    assert r == "R6" and "'Source of fibre'" in routing.escalation_reason


def test_r7_unmet_is_revise_with_what_to_fix():
    r, routing = rule(dossier(lbl(status=UNMET, explanation="No allergen statement."), clm()), claims=("Source of fibre",))
    assert r == "R7" and routing.route == Route.REVISE_AND_RECHECK
    assert "LBL-ALLERGEN (No allergen statement.)" in routing.reason and routing.escalation_reason is None


def test_r8_nothing_confirmed():
    r, routing = rule(dossier(lbl(status=NA)))
    assert r == "R8" and routing.route == Route.REGULATORY_REVIEW


def test_r9_clear_carries_the_not_an_approval_notice():
    r, routing = rule(dossier(lbl(), clm(), lbl("LBL-IRRADIATION", NA)), claims=("Source of fibre",))
    assert r == "R9" and routing.route == Route.CLEAR_FOR_PRINT and NOT_AN_APPROVAL in routing.reason


def test_unmet_is_never_cleared_whatever_else_is_met():
    for statuses in ([UNMET], [MET, UNMET], [MET, NA, UNMET]):
        d = dossier(*[lbl(f"LBL-{i}", s) for i, s in enumerate(statuses)])
        assert rule(d)[1].route != Route.CLEAR_FOR_PRINT


def test_long_lists_are_shortened():
    d = dossier(*[lbl(f"LBL-{i}", UNMET) for i in range(10)])
    assert "and 4 more" in rule(d)[1].reason


def test_route_records_its_rule():
    ctx = RunContext.new()
    routing = RuleRouter().route(request(), IN_SCOPE, dossier(lbl()), ACCEPT, ctx)
    step = ctx.steps[-1]
    assert step.kind == "routing" and step.output["rule"] == "R9" and step.output["route"] == routing.route.value
    assert step.input["statuses"] == {"LBL-ALLERGEN": "met"}


# ---------------------------------------------------------------- found in review: R6 is per claim

def sugar_low(status=MET):
    return finding("CLM-SUGARS-LOW", status, cite(SCHED["sugars"]), requirement="Condition for claim 'Low sugar'")


def test_r6_each_claim_needs_its_own_condition():
    """Two claims, only the fibre one checked: the unchecked 'Low sugar' must not be cleared."""
    r, routing = rule(dossier(lbl(), clm()), claims=("Source of fibre", "Low sugar"))
    assert r == "R6" and "'Low sugar'" in routing.escalation_reason and "Source of fibre" not in routing.escalation_reason


def test_r6_both_claims_checked_clears():
    r, _ = rule(dossier(lbl(), clm(), sugar_low()), claims=("Source of fibre", "Low sugar"))
    assert r == "R9"


def test_r6_single_claim_with_any_claim_finding_is_covered():
    """One claim and one CLM finding citing FSS-AC-2018: the finding is about that claim even if worded differently."""
    r, _ = rule(dossier(lbl(), finding("CLM-X", MET, cite(SCHED["fibre"]))), claims=("Rich in roughage",))
    assert r == "R9"
