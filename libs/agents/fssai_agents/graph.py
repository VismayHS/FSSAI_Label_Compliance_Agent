"""LangGraphPipeline: the whole run as a LangGraph graph (contexts/Namith.md M2.2). Day-0 skeleton.

It does what fssai_contracts.pipeline.ReferencePipeline does, node for node, and keeps the same edges
(checked by conformance.check_pipeline, and the reference tests in contracts/tests):
guardrails.screen_input -> classifier -> (researcher -> verifier) x max_research_attempts -> router
-> guardrails.filter_output. Flagged input, out-of-corpus category, an unverified answer, a hit loop bound or
ProviderUnavailable all end in regulatory-review; the last two with complete=False.

Switch on: IMPL_PIPELINE=fssai_agents.graph:LangGraphPipeline
"""
from __future__ import annotations

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import LabelCheckRequest, RunResult


class LangGraphPipeline:
    def __init__(self, guardrails, classifier, researcher, verifier, router) -> None:
        self.guardrails = guardrails
        self.classifier = classifier
        self.researcher = researcher
        self.verifier = verifier
        self.router = router

    @classmethod
    def from_registry(cls) -> LangGraphPipeline:
        from fssai_contracts.registry import build
        return cls(guardrails=build("guardrails"), classifier=build("classifier"),
                   researcher=build("researcher"), verifier=build("verifier"), router=build("router"))

    def run(self, request: LabelCheckRequest, ctx: RunContext) -> RunResult:
        raise NotImplementedError("M2.2: the LangGraph pipeline")
