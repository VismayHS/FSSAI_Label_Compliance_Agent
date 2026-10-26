"""Guardrails: screen every free-text field, filter every result (contexts/Namith.md M3.1, L4).

screen_input   runs the configured detectors over EVERY string in the request. Any flag blocks the run
               (the pipeline then routes to regulatory-review before any agent starts). The report names
               the field and the rule, never the attacker's text. One "guardrail" step per screen.
filter_output  can only make a result safer:
               - approval wording is removed (the system never approves a label);
               - a route of clear-for-print is forced to regulatory-review unless the verdict is accept and
                 every finding is met or not applicable with citations;
               - a revise-and-recheck on an unverified or incomplete run goes to regulatory-review;
               - any citation that does not resolve to text retrieved in this run is removed;
               - toxic output text is redacted;
               - the not-an-approval notice is restored if anything changed it.
               It never upgrades a route. One "guardrail" step per filter.

Switch on: IMPL_GUARDRAILS=fssai_guardrails.guardrails:Guardrails
"""
from __future__ import annotations

import re
import time

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    NOT_AN_APPROVAL, Citation, Finding, FindingStatus, GuardrailReport, LabelCheckRequest, Route, Routing,
    RunResult, VerifyAction,
)

from .detectors import Detector, Flag, LexiconToxicity, build_detectors
from .text import request_strings

AGENT = "guardrails"
REDACTED = "[approval wording removed]"
TOXIC_REDACTED = "[removed]"

# Wording that would approve a label. The route token "clear-for-print" (hyphens) is allowed: it is a route name.
APPROVAL_WORDING = [re.compile(p, re.IGNORECASE) for p in (
    r"\bapproved?\s+for\s+(print|printing|production|release|publication)\b",
    r"\bapprov(ed|al)\s+(granted|given|confirmed)\b",
    r"\b(label|pack|packaging|artwork|product|submission)\s+(is|are|was|has\s+been|have\s+been)\s+(hereby\s+)?(approved|cleared|certified|passed)\b",
    r"\b(we|i)\s+(hereby\s+)?(approve|certify|authori[sz]e)\b",
    r"\b(cleared|clear|safe|ready|good|ok|okay|fit)\s+(for|to)\s+(print|printing|publication|release)\b",
    r"\byou\s+(may|can)\s+(now\s+)?(go\s+ahead\s+and\s+)?print\b",
    r"\b(fully|100%)\s+compliant\b",
    r"\bcomplies\s+with\s+(all|every)\b",
)]
_SEVERITY = {Route.CLEAR_FOR_PRINT: 0, Route.REVISE_AND_RECHECK: 1, Route.REGULATORY_REVIEW: 2}


def _scrub(text: str) -> tuple[str, bool]:
    hit = False
    for rx in APPROVAL_WORDING:
        text, n = rx.subn(REDACTED, text)
        hit = hit or n > 0
    return text, hit


class Guardrails:
    def __init__(self, detectors: list[Detector] | None = None, output_toxicity=None) -> None:
        self.detectors = detectors if detectors is not None else build_detectors()
        self.output_toxicity = output_toxicity or LexiconToxicity()

    @classmethod
    def from_registry(cls) -> Guardrails:
        return cls()

    # ---------------------------------------------------------------- input

    def screen_input(self, request: LabelCheckRequest, ctx: RunContext) -> GuardrailReport:
        t0 = time.monotonic()
        fields = request_strings(request)
        flags: list[Flag] = []
        for detector in self.detectors:
            flags += detector.scan(fields, ctx)
        labels = list(dict.fromkeys(f.label for f in flags))
        rules: dict[str, list[str]] = {}
        for f in flags:
            rules.setdefault(f.label, [])
            if f.rule not in rules[f.label]:
                rules[f.label].append(f.rule)
        detail = "; ".join(f"{lab} ({', '.join(r)})" for lab, r in rules.items()) if labels else \
            f"{len(fields)} fields screened, none flagged"
        report = GuardrailReport(stage="input", allowed=not labels, flags=labels, detail=detail[:1000])
        ctx.record(agent=AGENT, kind="guardrail", name="screen_input", latency_ms=(time.monotonic() - t0) * 1000,
                   input={"fields_screened": len(fields), "detectors": [d.name for d in self.detectors]},
                   output=report.model_dump())
        return report

    # ---------------------------------------------------------------- output

    def filter_output(self, result: RunResult, ctx: RunContext) -> RunResult:
        t0 = time.monotonic()
        flags: list[str] = []
        retrieved = self._retrieved(result, ctx)

        findings = [self._clean_finding(f, retrieved, flags) for f in result.findings]
        routing = self._clean_routing(result.routing, flags)
        routing = self._safer_route(result, routing, findings, flags)

        verdict = result.verdict
        if verdict is not None:
            reason = verdict.escalation_reason
            if reason:
                cleaned, hit = self._clean_text(reason, "verdict.escalation_reason", flags)
                verdict = verdict.model_copy(update={"escalation_reason": cleaned}) if hit else verdict

        flags = list(dict.fromkeys(flags))
        report = GuardrailReport(stage="output", allowed=not flags, flags=flags,
                                 detail="; ".join(flags)[:1000] if flags else "output passed")
        ctx.record(agent=AGENT, kind="guardrail", name="filter_output", latency_ms=(time.monotonic() - t0) * 1000,
                   output=report.model_dump())
        return result.model_copy(update={
            "findings": findings, "routing": routing, "verdict": verdict,
            "guardrails": [*result.guardrails, report], "notice": NOT_AN_APPROVAL})

    # ---- pieces

    @staticmethod
    def _retrieved(result: RunResult, ctx: RunContext) -> dict[str, str]:
        """passage_id -> text for everything retrieved in this run (from the trace)."""
        out: dict[str, str] = {}
        for step in [*ctx.steps, *result.steps]:
            if step.kind != "tool" or not isinstance(step.output, dict):
                continue
            for p in step.output.get("passages", []) or []:
                if isinstance(p, dict) and p.get("passage_id"):
                    out[p["passage_id"]] = p.get("text", "")
        return out

    def _clean_text(self, text: str, where: str, flags: list[str]) -> tuple[str, bool]:
        changed = False
        text, hit = _scrub(text)
        if hit:
            flags.append(f"approval_wording:{where}")
            changed = True
        if self.output_toxicity.scan({where: text}, RunContext.new()):
            flags.append(f"toxicity:{where}")
            text, changed = TOXIC_REDACTED, True
        return text, changed

    def _clean_finding(self, f: Finding, retrieved: dict[str, str], flags: list[str]) -> Finding:
        kept: list[Citation] = []
        for c in f.citations:
            text = retrieved.get(c.passage_id)
            if text is not None and c.quote and c.quote in text:
                kept.append(c)
            else:
                flags.append(f"citation_removed:{f.requirement_id}")
        status = f.status
        explanation, _ = self._clean_text(f.explanation, f"finding.{f.requirement_id}.explanation", flags)
        requirement, _ = self._clean_text(f.requirement, f"finding.{f.requirement_id}.requirement", flags)
        if len(kept) < len(f.citations) and not kept and status in (FindingStatus.MET, FindingStatus.UNMET):
            status = FindingStatus.CANNOT_DETERMINE
            explanation = (explanation + " (Its citations could not be resolved to retrieved text.)").strip()
            flags.append(f"finding_downgraded:{f.requirement_id}")
        return f.model_copy(update={"citations": kept, "status": status, "explanation": explanation,
                                    "requirement": requirement})

    def _clean_routing(self, routing: Routing, flags: list[str]) -> Routing:
        reason, _ = self._clean_text(routing.reason, "routing.reason", flags)
        esc = routing.escalation_reason
        if esc:
            esc, _ = self._clean_text(esc, "routing.escalation_reason", flags)
        return routing.model_copy(update={"reason": reason, "escalation_reason": esc})

    def _safer_route(self, result: RunResult, routing: Routing, findings: list[Finding], flags: list[str]) -> Routing:
        problems: list[str] = []
        verdict = result.verdict
        accepted = verdict is not None and verdict.action == VerifyAction.ACCEPT
        if routing.route == Route.CLEAR_FOR_PRINT:
            if not result.complete:
                problems.append("run did not complete")
            if not accepted:
                problems.append("verdict is not accept")
            if not findings:
                problems.append("no findings")
            bad = [f.requirement_id for f in findings
                   if f.status not in (FindingStatus.MET, FindingStatus.NOT_APPLICABLE)
                   or (f.status == FindingStatus.MET and not f.citations)]
            if bad:
                problems.append("unmet, undetermined or uncited: " + ", ".join(bad))
        elif routing.route == Route.REVISE_AND_RECHECK:
            if not result.complete:
                problems.append("run did not complete")
            if verdict is not None and verdict.action != VerifyAction.ACCEPT:
                problems.append("verdict is not accept")
        if not problems:
            return routing
        flags.append(f"route_downgraded:{routing.route.value}")
        return Routing(route=Route.REGULATORY_REVIEW,
                       reason="Escalated by the output guardrail: " + "; ".join(problems) + ".",
                       escalation_reason=routing.escalation_reason or "; ".join(problems))
