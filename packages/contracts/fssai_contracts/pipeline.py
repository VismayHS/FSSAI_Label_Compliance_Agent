"""Reference pipeline: the agreed hand-off order, written as plain Python.

This is what the worker runs until the LangGraph pipeline (Namith) replaces it via
IMPL_PIPELINE. Any replacement must keep the same behaviour at the edges:

  guardrails.screen_input -> classifier -> (researcher -> verifier) x N -> router -> guardrails.filter_output

- Input flagged by guardrails        -> regulatory-review, no research.
- Category outside the corpus (F7)   -> regulatory-review, no research.
- Verifier says retry                -> research again with its hint, up to max_research_attempts.
- Still unverified after that        -> regulatory-review (A3: never return an unverified answer).
- Budget hit or provider unavailable -> complete=False, regulatory-review (A5).
"""
from __future__ import annotations

from .context import BudgetExceeded, RunContext
from .interfaces import ProviderUnavailable
from .schemas import (
    Classification, LabelCheckRequest, Route, Routing, RunResult, Verdict, VerifyAction,
)


class ReferencePipeline:
    def __init__(self, guardrails, classifier, researcher, verifier, router) -> None:
        self.guardrails = guardrails
        self.classifier = classifier
        self.researcher = researcher
        self.verifier = verifier
        self.router = router

    @classmethod
    def from_registry(cls) -> ReferencePipeline:
        from .registry import build
        return cls(guardrails=build("guardrails"), classifier=build("classifier"),
                   researcher=build("researcher"), verifier=build("verifier"), router=build("router"))

    def run(self, request: LabelCheckRequest, ctx: RunContext) -> RunResult:
        reports, classification, dossier, verdict = [], None, None, None
        try:
            screen = self.guardrails.screen_input(request, ctx)
            reports.append(screen)
            if not screen.allowed:
                return self._finish(ctx, True, reports, None, None, None, Routing(
                    route=Route.REGULATORY_REVIEW, reason="Input failed guardrail screening.",
                    escalation_reason=", ".join(screen.flags)))

            classification = self.classifier.classify(request, ctx)
            if not classification.in_scope:
                return self._finish(ctx, True, reports, classification, None, None, Routing(
                    route=Route.REGULATORY_REVIEW, reason="Product category is outside our corpus.",
                    escalation_reason=f"category '{classification.category}' not covered"))

            hint = None
            for _ in range(ctx.limits.max_research_attempts):
                ctx.check_budget()
                dossier = self.researcher.research(request, classification, ctx,
                                                   retry_hint=hint, previous=dossier)
                verdict = self.verifier.verify(request, dossier, ctx)
                if verdict.action != VerifyAction.RETRY:
                    break
                hint = verdict.retry_hint
            if verdict.action == VerifyAction.RETRY:
                verdict = Verdict(action=VerifyAction.ESCALATE, checks=verdict.checks,
                                  escalation_reason="still unverified after "
                                                    f"{ctx.limits.max_research_attempts} research attempts")

            routing = self.router.route(request, classification, dossier, verdict, ctx)
            return self._finish(ctx, True, reports, classification, dossier, verdict, routing)

        except (BudgetExceeded, ProviderUnavailable) as exc:
            ctx.event("run_incomplete", error=str(exc), error_type=type(exc).__name__)
            return self._finish(ctx, False, reports, classification, dossier, verdict, Routing(
                route=Route.REGULATORY_REVIEW, reason="Run did not complete; no confident answer.",
                escalation_reason=f"{type(exc).__name__}: {exc}"))

    def _finish(self, ctx: RunContext, complete: bool, reports, classification: Classification | None,
                dossier, verdict, routing: Routing) -> RunResult:
        result = RunResult(
            run_id=ctx.run_id, correlation_id=ctx.correlation_id, complete=complete, routing=routing,
            classification=classification, findings=dossier.findings if dossier else [],
            verdict=verdict, guardrails=reports,
        )
        if complete:
            result = self.guardrails.filter_output(result, ctx)
        return result.model_copy(update={"steps": list(ctx.steps), "totals": ctx.totals(),
                                         "prompt_versions": dict(ctx.prompt_versions)})
