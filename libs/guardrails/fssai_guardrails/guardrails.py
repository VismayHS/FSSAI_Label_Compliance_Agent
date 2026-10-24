"""Guardrails: screen every free-text label field, filter every result (contexts/Namith.md M3.1). Day-0 skeleton.

Rules (interface: fssai_contracts.interfaces.Guardrails; checked by conformance.check_guardrails):
- screen_input: every free-text field is hostile (LLM_Context §12.6). Flag injection, toxicity, over-long
  fields (GUARDRAIL_MAX_FIELD_CHARS) and control characters; flags name the field, e.g.
  "prompt_injection:label.front_of_pack_text". Record a "guardrail" step.
- filter_output: append an "output" GuardrailReport; it may downgrade a route or redact text, never upgrade
  a route and never drop the not-an-approval notice. Record a "guardrail" step.

Switch on: IMPL_GUARDRAILS=fssai_guardrails.guardrails:Guardrails
"""
from __future__ import annotations

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import GuardrailReport, LabelCheckRequest, RunResult


class Guardrails:
    def screen_input(self, request: LabelCheckRequest, ctx: RunContext) -> GuardrailReport:
        raise NotImplementedError("M3.1: injection, toxicity, length and control-character screening")

    def filter_output(self, result: RunResult, ctx: RunContext) -> RunResult:
        raise NotImplementedError("M3.1: output filtering; never upgrade a route")
