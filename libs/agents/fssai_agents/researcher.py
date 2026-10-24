"""LangGraphResearcher: the research agent, a LangGraph subgraph (contexts/Namith.md M2.1). Day-0 skeleton.

Tools: corpus_search, clause_lookup, request_field_lookup. The loop of spec §5: retrieve, look for a
modifying provision (the claim condition lives in the other regulation), search again from what was read.
Rules (interface: fssai_contracts.interfaces.Researcher; checked by conformance.check_researcher):
- call ctx.check_budget(tool_call=True) before every tool call and record a "tool" step whose output holds
  the full passages returned (D5);
- every Citation.quote is a verbatim span of a passage in dossier.passages (A3);
- a retry (retry_hint, previous) is attempt previous.attempt + 1 and should change strategy;
- conflicts, possible exemptions and missing conditions go in escalation_signals, never into guesses.

Switch on: IMPL_RESEARCHER=fssai_agents.researcher:LangGraphResearcher
"""
from __future__ import annotations

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Classification, LabelCheckRequest, ResearchDossier


class LangGraphResearcher:
    def __init__(self, retriever, llm, prompts) -> None:
        self.retriever = retriever
        self.llm = llm
        self.prompts = prompts

    @classmethod
    def from_registry(cls) -> LangGraphResearcher:
        from fssai_contracts.registry import build
        return cls(retriever=build("retriever"), llm=build("llm"), prompts=build("prompts"))

    def research(self, request: LabelCheckRequest, classification: Classification, ctx: RunContext, *,
                 retry_hint: str | None = None, previous: ResearchDossier | None = None) -> ResearchDossier:
        raise NotImplementedError("M2.1: the research subgraph with its three tools")
