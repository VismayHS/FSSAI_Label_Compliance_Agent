"""RuleRouter: explicit, documented routing rules (contexts/Vihaan.md V2.2; F6, F7).

Rules (interface: fssai_contracts.interfaces.Router; checked by conformance.check_router). They are
applied in order and the first that fires decides; each one is written up, with why, in
docs/decisions/201-vihaan-routing-rules.md:

  R1  verdict is not accept                         -> regulatory-review (A3: never route an unverified answer)
  R2  category outside the corpus                   -> regulatory-review (F7)
  R3  the dossier carries escalation signals        -> regulatory-review (conflict, exemption, missing condition)
  R4  no findings at all                            -> regulatory-review (nothing was checked, so nothing can clear)
  R5  any finding cannot_determine                  -> regulatory-review (also lists anything unmet, to fix)
  R6  a printed claim with no finding about it that
      cites the Claims regulation                   -> regulatory-review (the claim's condition was never established)
  R7  any finding unmet                             -> revise-and-recheck, listing what to fix
  R8  nothing was met (all not_applicable)          -> regulatory-review
  R9  everything met or not applicable              -> clear-for-print, with the not-an-approval notice

Every route carries a human-readable reason that starts with its rule id, and a "routing" step is recorded.
The system never approves a label: clear-for-print means "no problem found in what was checked".

Switch on: IMPL_ROUTER=fssai_verification.router:RuleRouter
"""
from __future__ import annotations

import time

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    NOT_AN_APPROVAL, Classification, Finding, FindingStatus, LabelCheckRequest, Regulation, ResearchDossier,
    Route, Routing, Verdict, VerifyAction,
)

from .checks import nutrient_of

AGENT = "router"
_MAX_LISTED = 6  # findings named in a reason before it says "and N more"


def _names(findings: list[Finding], with_explanation: bool = False) -> str:
    shown = [f"{f.requirement_id} ({f.explanation.strip()[:160]})" if with_explanation and f.explanation.strip()
             else f.requirement_id for f in findings[:_MAX_LISTED]]
    more = len(findings) - _MAX_LISTED
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def _about(f: Finding, claim: str) -> bool:
    """A finding is about a claim if it quotes the claim or names the same nutrient."""
    if claim.lower() in f"{f.requirement_id} {f.requirement} {f.explanation}".lower():
        return True
    want, got = nutrient_of(claim), nutrient_of(f"{f.requirement_id.replace('-', ' ')} {f.requirement}")
    return bool(want and got and want[1] == got[1])


def _claims_without_condition(request: LabelCheckRequest, dossier: ResearchDossier) -> list[str]:
    """Printed claims with no finding that cites FSS-AC-2018 for them: their condition was never looked at (R6).
    With a single claim, any claim finding (CLM-...) citing FSS-AC-2018 counts as being about it."""
    claims = request.label.claims
    on_claims_reg = [f for f in dossier.findings if any(c.regulation == Regulation.CLAIMS_2018 for c in f.citations)]
    missing = [c for c in claims if not any(_about(f, c) for f in on_claims_reg)]
    if len(claims) == 1 and missing and any(f.requirement_id.upper().startswith("CLM") for f in on_claims_reg):
        return []
    return missing


def decide(request: LabelCheckRequest, classification: Classification, dossier: ResearchDossier | None,
           verdict: Verdict) -> tuple[str, Routing]:
    """The rules as a pure function: (rule id, routing). Separate from route() so each rule is testable."""
    findings = dossier.findings if dossier else []

    if verdict.action != VerifyAction.ACCEPT:
        why = verdict.escalation_reason or (verdict.retry_hint and f"still unverified: {verdict.retry_hint}") \
            or "verification did not pass"
        return "R1", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason=f"[R1] The findings could not be verified against the retrieved regulation "
                                    f"text, so a person must review them: {why}")
    if not classification.in_scope:
        why = f"category '{classification.category}' is outside the corpus"
        return "R2", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason=f"[R2] The product category is not covered by our regulations: {why}.")
    if dossier and dossier.escalation_signals:
        why = "; ".join(dossier.escalation_signals)
        return "R3", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason=f"[R3] The research raised points a person must decide: {why}")
    if not findings:
        why = "no findings were produced"
        return "R4", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason="[R4] No requirement could be checked, so the label cannot be cleared.")

    undetermined = [f for f in findings if f.status == FindingStatus.CANNOT_DETERMINE]
    unmet = [f for f in findings if f.status == FindingStatus.UNMET]
    if undetermined:
        why = f"cannot determine: {_names(undetermined)}"
        fix = f" Also fix: {_names(unmet, True)}." if unmet else ""
        return "R5", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason=f"[R5] Some requirements cannot be decided from the regulation text: "
                                    f"{_names(undetermined, True)}.{fix}")
    missing = _claims_without_condition(request, dossier)
    if missing:
        why = "no claim condition was established for: " + "; ".join(f"'{c}'" for c in missing)
        return "R6", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason=f"[R6] The label makes claims whose conditions were not checked against the "
                                    f"Claims regulation: {why}.")
    if unmet:
        return "R7", Routing(route=Route.REVISE_AND_RECHECK,
                             reason=f"[R7] Revise the label and check it again. Not met: {_names(unmet, True)}.")
    if not any(f.status == FindingStatus.MET for f in findings):
        why = "no requirement was confirmed as met"
        return "R8", Routing(route=Route.REGULATORY_REVIEW, escalation_reason=why,
                             reason="[R8] Every finding was 'not applicable', so nothing confirms the label.")
    met = [f for f in findings if f.status == FindingStatus.MET]
    return "R9", Routing(route=Route.CLEAR_FOR_PRINT,
                         reason=f"[R9] All {len(findings)} checked requirements are met or not applicable, and "
                                f"every citation was verified ({_names(met)}). {NOT_AN_APPROVAL}")


class RuleRouter:
    def route(self, request: LabelCheckRequest, classification: Classification,
              dossier: ResearchDossier, verdict: Verdict, ctx: RunContext) -> Routing:
        ctx.check_budget()
        t0 = time.monotonic()
        rule, routing = decide(request, classification, dossier, verdict)
        ctx.record(agent=AGENT, kind="routing", name="route", latency_ms=(time.monotonic() - t0) * 1000,
                   input={"verdict": verdict.action.value,
                          "statuses": {f.requirement_id: f.status.value for f in (dossier.findings if dossier else [])}},
                   output={"rule": rule, **routing.model_dump(mode="json")})
        ctx.event("routed", rule=rule, route=routing.route.value)
        return routing
