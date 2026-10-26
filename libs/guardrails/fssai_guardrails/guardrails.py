"""Guardrails: screen every free-text label field, filter every result (contexts/Namith.md M3.1; L4).

screen_input  every free-text field of the request is hostile (LLM_Context §12.6): flagged for prompt injection,
              toxicity, over-length (GUARDRAIL_MAX_FIELD_CHARS) and control / invisible-direction characters. Flags
              name the field, e.g. "prompt_injection:label.front_of_pack_text" (plus the kind after a '/').
              Any flag blocks the run before an agent sees the text.
filter_output the last line of defence. It may downgrade a route or redact text, never upgrade a route and never drop
              the not-an-approval notice. It (1) redacts wording that approves a label for print, (2) forces
              regulatory-review if the route is clear-for-print but the verdict is not accept, a finding is not met or the
              run is incomplete, (3) removes citations that are not in this run's trace, (4) redacts toxic output.

Switch on: IMPL_GUARDRAILS=fssai_guardrails.guardrails:Guardrails
"""
from __future__ import annotations

import os
import re

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    NOT_AN_APPROVAL, Citation, Finding, FindingStatus, GuardrailReport, LabelCheckRequest, Route, Routing,
    RunResult, VerifyAction,
)

from .detectors import Detector, build_detectors

_SEVERITY = {Route.CLEAR_FOR_PRINT: 0, Route.REVISE_AND_RECHECK: 1, Route.REGULATORY_REVIEW: 2}
# C0/C1 controls except tab, newline and carriage return; bidi overrides and isolates; zero-width characters.
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩​-‏⁠﻿]")
_APPROVAL = [re.compile(p, re.I) for p in (
    r"\b(?:label|pack|packaging|product|artwork|claim)s?\s+(?:is|are|has been|have been|was|were)\s+(?:hereby\s+)?(?:approved|certified|passed|signed off)\b",
    r"\b(?:approved|certified|signed[- ]off)\s+(?:for\s+(?:print|printing|release|production)|by\s+(?:us|the system|fssai))\b",
    r"\b(?:we|i|the system)\s+(?:hereby\s+)?(?:approve|certify|authori[sz]e|sign off)\b",
    r"\bapprove[ds]?\s+(?:this|the|your)\s+label\b", r"\b(?:good|ready|safe|fit|cleared)\s+to\s+(?:print|go to print|be printed)\b",
    r"\bgo ahead (?:and|with) print(?:ing)?\b", r"\bno (?:further )?(?:review|changes?) (?:is |are )?(?:needed|required|necessary)\b",
    r"\bfully compliant and approved\b", r"\bpermitted for print\b",
)]
_NEGATION = re.compile(r"\b(?:not|never|cannot|can't|isn't|aren't|nor|no)\b(?:\W+\w+){0,2}\W*$", re.I)
REDACTED_APPROVAL = "[removed: this system cannot approve a label]"
REDACTED_TOXIC = "[removed: inappropriate language]"


def _max_chars() -> int:
    raw = os.environ.get("GUARDRAIL_MAX_FIELD_CHARS", "").split("#", 1)[0].strip()
    return int(raw) if raw else 4000


def request_fields(request: LabelCheckRequest) -> dict[str, str]:
    """Every free-text field of a request, by dotted path (list items as claims[i])."""
    label, pack = request.label, request.package
    fields: dict[str, str | None] = {
        "declared_category": request.declared_category, "client_reference": request.client_reference,
        "package.pack_type": pack.pack_type,
        "label.product_name": label.product_name, "label.brand_name": label.brand_name,
        "label.front_of_pack_text": label.front_of_pack_text, "label.ingredients": label.ingredients,
        "label.allergen_statement": label.allergen_statement, "label.fssai_licence_number": label.fssai_licence_number,
        "label.manufacturer_name_address": label.manufacturer_name_address, "label.date_marking": label.date_marking,
        "label.batch_or_lot": label.batch_or_lot, "label.other_text": label.other_text,
    }
    fields.update({f"label.claims[{i}]": c for i, c in enumerate(label.claims)})
    return {k: v for k, v in fields.items() if v}


class Guardrails:
    def __init__(self, detectors: dict[str, list[Detector]] | None = None) -> None:
        self.detectors = detectors if detectors is not None else build_detectors()

    @classmethod
    def from_registry(cls) -> Guardrails:
        return cls()

    # ------------------------------------------------------------------ input

    def screen_input(self, request: LabelCheckRequest, ctx: RunContext) -> GuardrailReport:
        limit = _max_chars()
        flags: list[str] = []
        for path, text in request_fields(request).items():
            if len(text) > limit:
                flags.append(f"too_long:{path}")
                continue  # do not scan megabytes of hostile text
            if _CONTROL.search(text):
                flags.append(f"control_characters:{path}")
            for det in self.detectors.get("injection", []):
                flags.extend(f"prompt_injection:{path}/{kind}" for kind in det.scan(text))
            for det in self.detectors.get("toxicity", []):
                flags.extend(f"toxicity:{path}/{kind}" for kind in det.scan(text))
        flags = list(dict.fromkeys(flags))
        report = GuardrailReport(stage="input", allowed=not flags, flags=flags,
                                 detail=f"{len(flags)} flag(s) in {len(request_fields(request))} free-text fields" if flags
                                 else f"{len(request_fields(request))} free-text fields screened")
        ctx.record(agent="guardrails", kind="guardrail", name="screen_input", output=report.model_dump())
        return report

    # ------------------------------------------------------------------ output

    def filter_output(self, result: RunResult, ctx: RunContext) -> RunResult:
        flags: list[str] = []
        route, reason, esc = result.routing.route, result.routing.reason, result.routing.escalation_reason

        reason, f1 = self._clean(reason, "routing.reason")
        esc, f2 = self._clean(esc, "routing.escalation_reason") if esc else (esc, [])
        flags += f1 + f2
        findings: list[Finding] = []
        passages = self._trace_passages(ctx)
        changed_evidence = False
        for f in result.findings:
            expl, fl = self._clean(f.explanation, f"finding.{f.requirement_id}.explanation")
            flags += fl
            kept = [c for c in f.citations if self._resolves(c, passages)]
            if len(kept) != len(f.citations):
                flags.append(f"unresolved_citation_removed:{f.requirement_id}")
            status = f.status
            if not kept and status != FindingStatus.CANNOT_DETERMINE and f.citations:
                status, changed_evidence = FindingStatus.CANNOT_DETERMINE, True
                expl = f"[citation removed: not found in this run's retrieved text] {expl}".strip()
            findings.append(f.model_copy(update={"explanation": expl, "citations": kept, "status": status}))

        forced = self._forced_reason(result, findings, changed_evidence, route)
        if forced and _SEVERITY[route] < _SEVERITY[Route.REGULATORY_REVIEW]:
            flags.append(f"route_downgraded:{route.value}")
            route = Route.REGULATORY_REVIEW
            esc = esc or forced
            reason = f"{reason} (Held for human review: {forced}.)"
        if any(x.startswith(("approval_wording", "toxicity")) for x in flags) and route == Route.CLEAR_FOR_PRINT:
            flags.append("route_downgraded:clear-for-print")
            route, esc = Route.REGULATORY_REVIEW, esc or "output contained wording this system must not issue"

        report = GuardrailReport(stage="output", allowed=not flags, flags=list(dict.fromkeys(flags)),
                                 detail="output unchanged" if not flags else "output was redacted or downgraded")
        ctx.record(agent="guardrails", kind="guardrail", name="filter_output", output=report.model_dump())
        routing = Routing(route=route, reason=reason, escalation_reason=esc)
        return result.model_copy(update={"routing": routing, "findings": findings, "notice": NOT_AN_APPROVAL,
                                         "guardrails": [*result.guardrails, report]})

    # ------------------------------------------------------------------ helpers

    def _clean(self, text: str, where: str) -> tuple[str, list[str]]:
        flags: list[str] = []
        for pattern in _APPROVAL:
            while True:
                m = next((x for x in pattern.finditer(text) if not _NEGATION.search(text[max(0, x.start() - 40):x.start()])), None)
                if m is None:
                    break
                text = text[:m.start()] + REDACTED_APPROVAL + text[m.end():]
                flags.append(f"approval_wording:{where}")
        if any(d.scan(text) for d in self.detectors.get("toxicity", [])):
            text = REDACTED_TOXIC
            flags.append(f"toxicity:{where}")
        return text, list(dict.fromkeys(flags))

    @staticmethod
    def _trace_passages(ctx: RunContext) -> dict[str, str]:
        out: dict[str, str] = {}
        for s in ctx.steps:
            if s.kind == "tool":
                for p in s.output.get("passages", []):
                    if isinstance(p, dict) and "passage_id" in p:
                        out[p["passage_id"]] = p.get("text", "")
        return out

    @staticmethod
    def _resolves(c: Citation, passages: dict[str, str]) -> bool:
        return c.passage_id in passages and bool(c.quote) and c.quote in passages[c.passage_id]

    @staticmethod
    def _forced_reason(result: RunResult, findings: list[Finding], changed: bool, route: Route) -> str | None:
        if route == Route.REGULATORY_REVIEW:
            return None
        if changed:
            return "a citation could not be resolved to retrieved text"
        if not result.complete:
            return "the run did not complete"
        if route == Route.CLEAR_FOR_PRINT:
            if result.verdict is None or result.verdict.action != VerifyAction.ACCEPT:
                return "the verifier did not accept the findings"
            if not findings or any(f.status not in (FindingStatus.MET, FindingStatus.NOT_APPLICABLE) for f in findings):
                return "a finding is not met"
        return None
