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
- A node that raises BudgetExceeded or ProviderUnavailable ends the run. run() streams the state after
  every node and keeps the last one; whatever was finished before the failure is still in the incomplete
  RunResult.

Checkpointing (extra; fssai_agents.checkpoints, PIPELINE_CHECKPOINTS). The live RunContext is LangGraph's
runtime context, never part of the state, so the state is plain contract models and can be saved after every
node, under the run id. The state also carries the trace so far (`steps`, `prompt_versions`). When a run with
the same id starts again (RQ re-queues the job of a worker that died), run() restores that trace into the new
context and continues at the node that was interrupted: finished nodes do not run again, so their LLM calls
are not paid for twice. A run that returns a result (complete or not) deletes its checkpoint; one that is
interrupted (the process dies, or an unexpected exception escapes) keeps it.

Switch on: IMPL_PIPELINE=fssai_agents.graph:LangGraphPipeline
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.runtime import Runtime

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import (
    Classification, GuardrailReport, LabelCheckRequest, ResearchDossier, Route, Routing, RunResult, StepRecord,
    Verdict, VerifyAction,
)

from . import checkpoints, metrics


class RunState(TypedDict, total=False):
    """Only contract models and plain data, so a checkpointer can save it. The RunContext is not here: nodes get
    it as runtime.context."""
    request: LabelCheckRequest
    reports: list[GuardrailReport]
    classification: Classification | None
    dossier: ResearchDossier | None
    verdict: Verdict | None
    hint: str | None
    attempts: int
    max_attempts: int
    routing: Routing | None
    result: RunResult | None
    steps: list[StepRecord]          # the trace so far; restored into the context when a run resumes
    prompt_versions: dict[str, str]


class LangGraphPipeline:
    def __init__(self, guardrails, classifier, researcher, verifier, router, checkpointer=None) -> None:
        self.guardrails = guardrails
        self.classifier = classifier
        self.researcher = researcher
        self.verifier = verifier
        self.router = router
        self.checkpointer = checkpointer
        self.graph = self._build()

    @classmethod
    def from_registry(cls) -> LangGraphPipeline:
        from fssai_contracts.registry import build
        return cls(guardrails=build("guardrails"), classifier=build("classifier"),
                   researcher=build("researcher"), verifier=build("verifier"), router=build("router"),
                   checkpointer=checkpoints.from_env())

    # ---- graph

    def _build(self):
        g = StateGraph(RunState, context_schema=RunContext)
        for name, fn in (("screen", self._screen), ("classify", self._classify), ("research", self._research),
                         ("verify", self._verify), ("route", self._route), ("finish", self._finish_node)):
            g.add_node(name, _with_trace(fn))
        g.set_entry_point("screen")
        g.add_conditional_edges("screen", lambda s: "finish" if s.get("routing") else "classify",
                                {"finish": "finish", "classify": "classify"})
        g.add_conditional_edges("classify", lambda s: "finish" if s.get("routing") else "research",
                                {"finish": "finish", "research": "research"})
        g.add_edge("research", "verify")
        g.add_conditional_edges("verify", self._after_verify, {"research": "research", "route": "route"})
        g.add_edge("route", "finish")
        g.add_edge("finish", END)
        return g.compile(checkpointer=self.checkpointer)

    # ---- nodes (same order and semantics as ReferencePipeline.run)

    def _screen(self, s: RunState, ctx: RunContext) -> RunState:
        report = self.guardrails.screen_input(s["request"], ctx)
        update: RunState = {"reports": [*s["reports"], report]}
        if not report.allowed:
            update["routing"] = Routing(route=Route.REGULATORY_REVIEW, reason="Input failed guardrail screening.",
                                        escalation_reason=", ".join(report.flags))
        return update

    def _classify(self, s: RunState, ctx: RunContext) -> RunState:
        classification = self.classifier.classify(s["request"], ctx)
        update: RunState = {"classification": classification}
        if not classification.in_scope:
            update["routing"] = Routing(route=Route.REGULATORY_REVIEW, reason="Product category is outside our corpus.",
                                        escalation_reason=f"category '{classification.category}' not covered")
        return update

    def _research(self, s: RunState, ctx: RunContext) -> RunState:
        ctx.check_budget()
        dossier = self.researcher.research(s["request"], s["classification"], ctx,
                                           retry_hint=s.get("hint"), previous=s.get("dossier"))
        return {"dossier": dossier, "attempts": s["attempts"] + 1}

    def _verify(self, s: RunState, ctx: RunContext) -> RunState:
        verdict = self.verifier.verify(s["request"], s["dossier"], ctx)
        update: RunState = {"verdict": verdict}
        if verdict.action == VerifyAction.RETRY:
            update["hint"] = verdict.retry_hint
        return update

    def _after_verify(self, s: RunState) -> str:
        if s["verdict"].action == VerifyAction.RETRY and s["attempts"] < s["max_attempts"]:
            metrics.record_retry("researcher")
            return "research"
        return "route"

    def _route(self, s: RunState, ctx: RunContext) -> RunState:
        verdict = s["verdict"]
        if verdict.action == VerifyAction.RETRY:  # attempts used up: never return an unverified answer
            verdict = Verdict(action=VerifyAction.ESCALATE, checks=verdict.checks,
                              escalation_reason=f"still unverified after {ctx.limits.max_research_attempts} research attempts")
        routing = self.router.route(s["request"], s["classification"], s["dossier"], verdict, ctx)
        return {"verdict": verdict, "routing": routing}

    def _finish_node(self, s: RunState, ctx: RunContext) -> RunState:
        return {"result": self._result(s, ctx, complete=True, routing=s["routing"])}

    # ---- result

    def _result(self, s: RunState, ctx: RunContext, *, complete: bool, routing: Routing) -> RunResult:
        dossier = s.get("dossier")
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
        limit = 12 + 4 * max(1, ctx.limits.max_research_attempts)
        config: dict[str, Any] = {"recursion_limit": limit}
        start: RunState | None = {
            "request": request, "reports": [], "classification": None, "dossier": None, "verdict": None,
            "hint": None, "attempts": 0, "max_attempts": ctx.limits.max_research_attempts, "routing": None,
            "result": None, "steps": [], "prompt_versions": {}}
        if self.checkpointer is not None:
            config["configurable"] = {"thread_id": ctx.run_id}
            resumed = self._resume(request, ctx, config)
            if isinstance(resumed, RunResult):  # the graph had finished; the process died before the save
                self._forget(ctx.run_id)
                return resumed
            if resumed is not None:
                start = None  # LangGraph continues from the saved checkpoint
        last: dict[str, Any] = dict(start) if start is not None else dict(self.graph.get_state(config).values)
        try:
            for snapshot in self.graph.stream(start, config=config, context=ctx, stream_mode="values"):
                last = snapshot
            result = last["result"]
        except (BudgetExceeded, ProviderUnavailable) as exc:
            ctx.event("run_incomplete", error=str(exc), error_type=type(exc).__name__)
            result = self._result(last, ctx, complete=False, routing=Routing(
                route=Route.REGULATORY_REVIEW, reason="Run did not complete; no confident answer.",
                escalation_reason=f"{type(exc).__name__}: {exc}"))  # type: ignore[arg-type]
        # The run has a result, so its checkpoint is done with. An exception that escapes (a crash) keeps the
        # checkpoint, exactly as a process that dies does, so the same run id can continue where it stopped.
        self._forget(ctx.run_id)
        return result

    # ---- checkpoints

    def _resume(self, request: LabelCheckRequest, ctx: RunContext, config: dict) -> RunResult | str | None:
        """What a checkpoint under this run id says: None (start fresh), the RunResult of a graph that had already
        finished, or the name of the node to continue at. In the last two cases the saved trace is restored into
        ctx, so step and tool-call budgets count what was already done."""
        saved = self.graph.get_state(config)
        values = saved.values or {}
        if not values:
            return None
        if values.get("request") != request:  # same id, different request: never mix two runs
            ctx.event("checkpoint_discarded", reason="request differs")
            self._forget(ctx.run_id)
            return None
        ctx.steps[:] = list(values.get("steps") or [])
        ctx.prompt_versions.update(values.get("prompt_versions") or {})
        at = saved.next[0] if saved.next else "finished"
        ctx.event("run_resumed", at=at, steps_restored=len(ctx.steps), attempts=values.get("attempts", 0))
        metrics.record_resume(at)
        if not saved.next and values.get("result") is not None:
            return values["result"]
        return at

    def _forget(self, run_id: str) -> None:
        if self.checkpointer is None:
            return
        try:
            self.checkpointer.delete_thread(run_id)
        except Exception:  # noqa: BLE001 - a leftover checkpoint costs disk space, never a run
            pass


def _with_trace(fn):
    """A graph node from a method taking (state, ctx): passes runtime.context in, and adds the trace so far to the
    update, so that every checkpoint holds it."""
    def node(s: RunState, runtime: Runtime[RunContext]) -> RunState:
        ctx = runtime.context
        update = fn(s, ctx)
        update["steps"] = list(ctx.steps)
        update["prompt_versions"] = dict(ctx.prompt_versions)
        return update
    node.__name__ = getattr(fn, "__name__", "node")
    return node
