"""RuleRouter: explicit, documented routing rules (contexts/Vihaan.md V2.2). Day-0 skeleton.

Rules (interface: fssai_contracts.interfaces.Router; checked by conformance.check_router):
- a verdict other than accept -> regulatory-review with an escalation_reason (A3, F7);
- any unmet or undetermined finding is never clear-for-print;
- every route carries a human-readable reason; record a "routing" step. The system never approves a label.

Switch on: IMPL_ROUTER=fssai_verification.router:RuleRouter
"""
from __future__ import annotations

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Classification, LabelCheckRequest, ResearchDossier, Routing, Verdict


class RuleRouter:
    def route(self, request: LabelCheckRequest, classification: Classification,
              dossier: ResearchDossier, verdict: Verdict, ctx: RunContext) -> Routing:
        raise NotImplementedError("V2.2: the routing rules")
