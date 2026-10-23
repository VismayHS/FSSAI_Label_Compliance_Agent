"""The seams between owners. Each Protocol has a fake in fakes.py and a real
implementation in its owner's package, selected at runtime by registry.py.

Owner of the real implementation is noted on each Protocol.
"""
from __future__ import annotations

from typing import Protocol

from .context import RunContext
from .schemas import (
    Classification, GateDecision, GuardrailReport, LabelCheckRequest, LLMMessage,
    LLMResponse, Passage, PromptTemplate, Regulation, ResearchDossier, Routing,
    RunResult, RunStatus, Verdict,
)


class ProviderUnavailable(RuntimeError):
    """The LLM provider failed after bounded retries, or the circuit breaker is open."""


class RequestGate(Protocol):  # Vihaan: libs/gate
    """Ingestion boundary: rate limit, validate, quarantine rejects. No agent run starts on reject."""
    def check(self, raw: dict, client_id: str) -> GateDecision: ...


class Retriever(Protocol):  # Nishkal: libs/retrieval
    def search(self, query: str, ctx: RunContext, *, k: int = 5,
               regulation: Regulation | None = None) -> list[Passage]: ...

    def get_clause(self, regulation: Regulation, clause_id: str, ctx: RunContext) -> Passage | None: ...


class LLMClient(Protocol):  # Vismay: libs/llm_gateway
    """Records its own "llm" step on ctx. Raises ProviderUnavailable instead of hanging."""
    def complete(self, messages: list[LLMMessage], ctx: RunContext, *, agent: str, step: str,
                 prompt: PromptTemplate | None = None, json_mode: bool = False) -> LLMResponse: ...


class PromptStore(Protocol):  # Namith: libs/prompts
    def get(self, name: str, version: str | None = None) -> PromptTemplate: ...


class Guardrails(Protocol):  # Namith: libs/guardrails
    def screen_input(self, request: LabelCheckRequest, ctx: RunContext) -> GuardrailReport: ...

    def filter_output(self, result: RunResult, ctx: RunContext) -> RunResult:
        """May downgrade the route or redact text; appends an "output" GuardrailReport."""
        ...


class Classifier(Protocol):  # Namith: libs/agents
    def classify(self, request: LabelCheckRequest, ctx: RunContext) -> Classification: ...


class Researcher(Protocol):  # Namith: libs/agents
    def research(self, request: LabelCheckRequest, classification: Classification, ctx: RunContext, *,
                 retry_hint: str | None = None,
                 previous: ResearchDossier | None = None) -> ResearchDossier: ...


class Verifier(Protocol):  # Vihaan: libs/verification
    def verify(self, request: LabelCheckRequest, dossier: ResearchDossier, ctx: RunContext) -> Verdict: ...


class Router(Protocol):  # Vihaan: libs/verification
    def route(self, request: LabelCheckRequest, classification: Classification,
              dossier: ResearchDossier, verdict: Verdict, ctx: RunContext) -> Routing: ...


class Pipeline(Protocol):  # Namith: libs/agents (LangGraph). Reference version: pipeline.py
    def run(self, request: LabelCheckRequest, ctx: RunContext) -> RunResult: ...


class RunStore(Protocol):  # Vismay: services/api + services/worker
    def save(self, status: RunStatus) -> None: ...

    def get(self, run_id: str) -> RunStatus | None: ...

    def recent(self, limit: int = 50) -> list[RunStatus]: ...
