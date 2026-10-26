"""LangGraphPipeline: the whole run as a LangGraph graph (docs/contexts/Namith.md M2.2).

It does what fssai_contracts.pipeline.ReferencePipeline does, node for node, and keeps the same edges
(checked by conformance.check_pipeline and by tests/test_contract_parity.py):

    screen -> classify -> research -> verify -> (retry: research | route) -> route -> finish
       |          |                                                                    ^
       +----------+--- blocked input / out-of-corpus category -----------------------+

- Flagged input, out-of-corpus category, an unverified answer, a hit loop bound or ProviderUnavailable
  all end in regulatory-review; the last two with complete=False (A5).
- The verifier says retry: the researcher runs again with its hint and the previous dossier, up to
  ctx.limits.max_research_attempts. Still retry after that: the verdict becomes escalate (A3).
- A node that raises BudgetExceeded or ProviderUnavailable ends the run. LangGraph loses the state of a
  run that raises, so run() streams the state after every node and keeps the last one; whatever was
  finished before the failure is still in the incomplete RunResult.

Switch on: IMPL_PIPELINE=fssai_agents.graph:LangGraphPipeline
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import (
    Classification, GuardrailReport, LabelCheckRequest, ResearchDossier, Route, Routing, RunResult, Verdict,
    VerifyAction,
)

from . import metrics


class RunState(TypedDict, total=False):
    ctx: RunContext
    request: LabelCheckRequest
    reports: list[GuardrailReport]
    classification: Classification | None
    dossier: ResearchDossier | None
    verdict: Verdict | None
    hint: str | None
    attempts: int
    routing: Routing | None
    result: RunResult | None


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

    # ---- graph

    def _build(self):
        g = StateGraph(RunState)
        g.add_node("screen", self._screen)
        g.add_node("classify", self._classify)
        g.add_node("research", self._research)
        g.add_node("verify", self._verify)
        g.add_node("route", self._route)
        g.add_node("finish", self._finish_node)
        g.set_entry_point("screen")
        g.add_conditional_edges("screen", lambda s: "finish" if s.get("routing") else "classify",
                                {"finish": "finish", "classify": "classify"})
        g.add_conditional_edges("classify", lambda s: "finish" if s.get("routing") else "research",
                                {"finish": "finish", "research": "research"})
        g.add_edge("research", "verify")
        g.add_conditional_edges("verify", self._after_verify, {"research": "research", "route": "route"})
        g.add_edge("route", "finish")
        g.add_edge("finish", END)
        return g.compile()

    # ---- nodes (same order and semantics as ReferencePipeline.run)

    def _screen(self, s: RunState) -> RunState:
        report = self.guardrails.screen_input(s["request"], s["ctx"])
        update: RunState = {"reports": [*s["reports"], report]}
        if not report.allowed:
            update["routing"] = Routing(route=Route.REGULATORY_REVIEW, reason="Input failed guardrail screening.",
                                        escalation_reason=", ".join(report.flags))
        return update

    def _classify(self, s: RunState) -> RunState:
        classification = self.classifier.classify(s["request"], s["ctx"])
        update: RunState = {"classification": classification}
        if not classification.in_scope:
            update["routing"] = Routing(route=Route.REGULATORY_REVIEW, reason="Product category is outside our corpus.",
                                        escalation_reason=f"category '{classification.category}' not covered")
        return update

    def _research(self, s: RunState) -> RunState:
        ctx = s["ctx"]
        ctx.check_budget()
        dossier = self.researcher.research(s["request"], s["classification"], ctx,
                                           retry_hint=s.get("hint"), previous=s.get("dossier"))
        return {"dossier": dossier, "attempts": s["attempts"] + 1}

    def _verify(self, s: RunState) -> RunState:
        verdict = self.verifier.verify(s["request"], s["dossier"], s["ctx"])
        update: RunState = {"verdict": verdict}
        if verdict.action == VerifyAction.RETRY:
            update["hint"] = verdict.retry_hint
        return update

    def _after_verify(self, s: RunState) -> str:
        if s["verdict"].action == VerifyAction.RETRY and s["attempts"] < s["ctx"].limits.max_research_attempts:
            metrics.record_retry("researcher")
            return "research"
        return "route"

    def _route(self, s: RunState) -> RunState:
        verdict, ctx = s["verdict"], s["ctx"]
        if verdict.action == VerifyAction.RETRY:  # attempts used up: never return an unverified answer
            verdict = Verdict(action=VerifyAction.ESCALATE, checks=verdict.checks,
                              escalation_reason=f"still unverified after {ctx.limits.max_research_attempts} research attempts")
        routing = self.router.route(s["request"], s["classification"], s["dossier"], verdict, ctx)
        return {"verdict": verdict, "routing": routing}

    def _finish_node(self, s: RunState) -> RunState:
        return {"result": self._result(s, complete=True, routing=s["routing"])}

    # ---- result

    def _result(self, s: RunState, *, complete: bool, routing: Routing) -> RunResult:
        ctx, dossier = s["ctx"], s.get("dossier")
        result = RunResult(
            run_id=ctx.run_id, correlation_id=ctx.correlation_id, complete=complete, routing=routing,
            classification=s.get("classification"), findings=dossier.findings if dossier else [],
            verdict=s.get("verdict"), guardrails=list(s.get("reports", [])))
        if complete:
            result = self.guardrails.filter_output(result, ctx)
        result = result.model_copy(update={"steps": list(ctx.steps), "totals": ctx.totals(),
                                           "prompt_versions": dict(ctx.prompt_versions)})
        metrics.observe_run(result, ctx)  # per-agent metrics for the dashboard (M3.3)
        return result

    # ---- seam

    def run(self, request: LabelCheckRequest, ctx: RunContext) -> RunResult:
        state: RunState = {"ctx": ctx, "request": request, "reports": [], "classification": None, "dossier": None,
                           "verdict": None, "hint": None, "attempts": 0, "routing": None, "result": None}
        last: dict[str, Any] = dict(state)
        try:
            limit = 12 + 4 * max(1, ctx.limits.max_research_attempts)
            for snapshot in self.graph.stream(state, config={"recursion_limit": limit}, stream_mode="values"):
                last = snapshot
            return last["result"]
        except (BudgetExceeded, ProviderUnavailable) as exc:
            ctx.event("run_incomplete", error=str(exc), error_type=type(exc).__name__)
            return self._result(last, complete=False, routing=Routing(
                route=Route.REGULATORY_REVIEW, reason="Run did not complete; no confident answer.",
                escalation_reason=f"{type(exc).__name__}: {exc}"))  # type: ignore[arg-type]
