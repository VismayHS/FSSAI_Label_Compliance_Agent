"""LLMClassifier: product category and claims (contexts/Namith.md M1.2). Day-0 skeleton.

Rules (interface: fssai_contracts.interfaces.Classifier; checked by conformance.check_classifier):
- in_scope is False for any category outside CORPUS_CATEGORIES (F7: escalate, never guess);
- every printed claim becomes a DetectedClaim with claim_type and nutrient ("Source of protein" -> protein);
- label text is untrusted: it goes in the user message, never in the system prompt;
- LLM calls go through self.llm (which records the llm step); record a "classification" step with the result.

Switch on: IMPL_CLASSIFIER=fssai_agents.classifier:LLMClassifier
"""
from __future__ import annotations

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Classification, LabelCheckRequest


class LLMClassifier:
    def __init__(self, llm, prompts) -> None:
        self.llm = llm
        self.prompts = prompts

    @classmethod
    def from_registry(cls) -> LLMClassifier:
        from fssai_contracts.registry import build
        return cls(llm=build("llm"), prompts=build("prompts"))

    def classify(self, request: LabelCheckRequest, ctx: RunContext) -> Classification:
        raise NotImplementedError("M1.2: classify the category and detect claims")
