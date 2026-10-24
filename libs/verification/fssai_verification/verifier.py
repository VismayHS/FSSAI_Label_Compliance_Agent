"""AgentVerifier: the second agent; checks every finding against retrieved text (contexts/Vihaan.md V2.1). Day-0 skeleton.

Tools: resolve_citation, clause_lookup. Rules (interface: fssai_contracts.interfaces.Verifier;
checked by conformance.check_verifier):
- a citation is supported only if its passage was retrieved in this run and its quote is verbatim text of it;
- accept only when every finding is supported; retry (with a retry_hint for a different strategy) when
  re-searching could fix it; escalate when the dossier carries escalation_signals or retrying is pointless;
- one FindingCheck per finding; record a "verification" step.

Switch on: IMPL_VERIFIER=fssai_verification.verifier:AgentVerifier
"""
from __future__ import annotations

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import LabelCheckRequest, ResearchDossier, Verdict


class AgentVerifier:
    def __init__(self, retriever, llm, prompts) -> None:
        self.retriever = retriever
        self.llm = llm
        self.prompts = prompts

    @classmethod
    def from_registry(cls) -> AgentVerifier:
        from fssai_contracts.registry import build
        return cls(retriever=build("retriever"), llm=build("llm"), prompts=build("prompts"))

    def verify(self, request: LabelCheckRequest, dossier: ResearchDossier, ctx: RunContext) -> Verdict:
        raise NotImplementedError("V2.1: the verifier agent")
