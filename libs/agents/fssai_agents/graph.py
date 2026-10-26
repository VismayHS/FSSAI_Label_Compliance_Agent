"""LangGraphPipeline: the whole run as a LangGraph graph (contexts/Namith.md M2.2; A2).

It does what fssai_contracts.pipeline.ReferencePipeline does, node for node, with the same edges (checked by
conformance.check_pipeline and by tests/test_contract_parity.py, which runs the reference pipeline's scenarios):

    guard_in -> classify -> research -> verify -> route -> finish (output filter)
                   |            ^          |
                   |            +-- retry -+   (verdict "retry", at most max_research_attempts rounds)
                   +-> finish   (flagged input or category outside the corpus: no research)

* Flagged input, out-of-corpus category, an unverified answer after the last attempt -> regulatory-review.
* BudgetExceeded or ProviderUnavailable anywhere -> complete=False, regulatory-review: never a confident answer (A5).
* Each node is one agent with its own tools, state and prompt; they meet only through the hand-off schemas
  (Classification, ResearchDossier, Verdict, Routing). docs/agent-topology.md says what happens when each one fails.

Run state shared by the nodes lives in a _RunState, so an exception half-way still leaves everything done so far
available for the incomplete result.

Switch on: IMPL_PIPELINE=fssai_agents.graph:LangGraphPipeline
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import metrics

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import (
    Classification, GuardrailReport, LabelCheckRequest, ResearchDossier, Route, Routing, RunResult, Verdict,
    VerifyAction,
)


class _S(TypedDict, total=False):
    attempts: int


@dataclass
class _RunState:
    request: LabelCheckRequest
    ctx: RunContext
    reports: list[GuardrailReport] = field(default_factory=list)
    classification: Classification | None = None
    dossier: ResearchDossier | None = None
    verdict: Verdict | None = None
    routing: Routing | None = None
    hint: str | None = None


class LangGraphPipeline:
    def __init__(self, guardrails, classifier, researcher, verifier, router) -> None:
        self.guardrails = guardrails
        self.classifier = classifier
        self.researcher = researcher
        self.verifier = verifier
        self.router = router
        self.graph = self._build()

    @classmethod
    def from_registry(cls) -> LangGraphPipeline:
        from fssai_contracts.registry import build
        return cls(guardrails=build("guardrails"), classifier=build("classifier"),
                   researcher=build("researcher"), verifier=build("verifier"), router=build("router"))

    # ------------------------------------------------------------------ public

    def run(self, request: LabelCheckRequest, ctx: RunContext) -> RunResult:
        st = _RunState(request=request, ctx=ctx)
        complete = True
        try:
            self.graph.invoke({"attempts": 0}, config={"configurable": {"run": st},
                                                       "recursion_limit": 12 + 4 * max(1, ctx.limits.max_research_attempts)})
        except (BudgetExceeded, ProviderUnavailable) as exc:
            complete = False
            ctx.event("run_incomplete", error=str(exc), error_type=type(exc).__name__)
            st.routing = Routing(route=Route.REGULATORY_REVIEW, reason="Run did not complete; no confident answer.",
                                 escalation_reason=f"{type(exc).__name__}: {exc}")
        return self._finish(st, complete)

    # ------------------------------------------------------------------ graph

    def _build(self):
        g = StateGraph(_S)
        g.add_node("guard_in", self._guard_in)
        g.add_node("classify", self._classify)
        g.add_node("research", self._research)
        g.add_node("verify", self._verify)
        g.add_node("route", self._route)
        g.add_edge(START, "guard_in")
        g.add_conditional_edges("guard_in", self._after_guard, {"classify": "classify", "end": END})
        g.add_conditional_edges("classify", self._after_classify, {"research": "research", "end": END})
        g.add_edge("research", "verify")
        g.add_conditional_edges("verify", self._after_verify, {"research": "research", "route": "route"})
        g.add_edge("route", END)
        return g.compile()

    # Each node reads the shared run state from config; the graph state carries only the attempt counter.

    def _guard_in(self, state: _S, config) -> dict:
        st = config["configurable"]["run"]
        screen = self.guardrails.screen_input(st.request, st.ctx)
        st.reports.append(screen)
        if not screen.allowed:
            st.routing = Routing(route=Route.REGULATORY_REVIEW, reason="Input failed guardrail screening.",
                                 escalation_reason=", ".join(screen.flags))
        return {}

    def _after_guard(self, state: _S, config) -> str:
        return "end" if config["configurable"]["run"].routing else "classify"

    def _classify(self, state: _S, config) -> dict:
        st = config["configurable"]["run"]
        st.classification = self.classifier.classify(st.request, st.ctx)
        if not st.classification.in_scope:
            st.routing = Routing(route=Route.REGULATORY_REVIEW, reason="Product category is outside our corpus.",
                                 escalation_reason=f"category '{st.classification.category}' not covered")
        return {}

    def _after_classify(self, state: _S, config) -> str:
        return "end" if config["configurable"]["run"].routing else "research"

    def _research(self, state: _S, config) -> dict:
        st = config["configurable"]["run"]
        st.ctx.check_budget()
        st.dossier = self.researcher.research(st.request, st.classification, st.ctx,
                                              retry_hint=st.hint, previous=st.dossier)
        return {"attempts": state.get("attempts", 0) + 1}

    def _verify(self, state: _S, config) -> dict:
        st = config["configurable"]["run"]
        st.verdict = self.verifier.verify(st.request, st.dossier, st.ctx)
        return {}

    def _after_verify(self, state: _S, config) -> str:
        st = config["configurable"]["run"]
        if st.verdict.action != VerifyAction.RETRY:
            return "route"
        if state.get("attempts", 0) < st.ctx.limits.max_research_attempts:
            st.hint = st.verdict.retry_hint
            st.ctx.event("research_retry", attempt=state.get("attempts", 0), hint=st.hint)
            metrics.record_retry("researcher")
            return "research"
        st.verdict = Verdict(action=VerifyAction.ESCALATE, checks=st.verdict.checks,
                             escalation_reason="still unverified after "
                                               f"{st.ctx.limits.max_research_attempts} research attempts")
        return "route"

    def _route(self, state: _S, config) -> dict:
        st = config["configurable"]["run"]
        st.routing = self.router.route(st.request, st.classification, st.dossier, st.verdict, st.ctx)
        return {}

    # ------------------------------------------------------------------ result

    def _finish(self, st: _RunState, complete: bool) -> RunResult:
        ctx = st.ctx
        result = RunResult(
            run_id=ctx.run_id, correlation_id=ctx.correlation_id, complete=complete, routing=st.routing,
            classification=st.classification, findings=st.dossier.findings if st.dossier else [],
            verdict=st.verdict, guardrails=list(st.reports))
        if complete:
            result = self.guardrails.filter_output(result, ctx)
        result = result.model_copy(update={"steps": list(ctx.steps), "totals": ctx.totals(),
                                           "prompt_versions": dict(ctx.prompt_versions)})
        metrics.observe_run(result, ctx)
        return result
