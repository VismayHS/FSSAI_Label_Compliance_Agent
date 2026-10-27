"""A full run (guardrails, classifier, researcher with the sweep, the REAL verifier and router) stays inside
RUN_MAX_STEPS=25, RUN_MAX_TOOL_CALLS=15 even when the verifier sends the researcher back twice.

The LLM is scripted by step name, so this measures step and tool-call counts, not model quality or wall time
(the sweep adds no LLM calls, so it adds retrieval time only). Run with -s to print the numbers."""
import json

import pytest

from fssai_agents.graph import LangGraphPipeline
from fssai_agents.researcher import LangGraphResearcher
from fssai_contracts.conformance import sample_request
from fssai_contracts.context import RunContext, RunLimits
from fssai_contracts.fakes import FAKE_PASSAGES, FakeRetriever
from fssai_contracts.schemas import Classification, DetectedClaim, LLMResponse
from fssai_guardrails.guardrails import Guardrails
from fssai_prompts.store import FilePromptStore
from fssai_verification.router import RuleRouter
from fssai_verification.verifier import AgentVerifier

AC = next(p for p in FAKE_PASSAGES if p.passage_id == "fake-ac-protein")
LD = next(p for p in FAKE_PASSAGES if p.passage_id == "fake-ld-nutrition")


class StubClassifier:
    """Costs what the real one costs: a classification step and one LLM step."""
    def classify(self, request, ctx):
        ctx.check_budget()
        ctx.record(agent="classifier", kind="llm", name="classify")
        ctx.record(agent="classifier", kind="classification", name="classify")
        return Classification(category=request.declared_category, in_scope=True,
                              claims=[DetectedClaim(text="Source of protein", claim_type="nutrient_content",
                                                    nutrient="protein")])


class ScriptedLLM:
    def __init__(self, support, busy=False):
        self.support, self.busy, self.n, self.ids = support, busy, 0, []

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        ctx.record(agent=agent, kind="llm", name=step, prompt_name=prompt.name, prompt_version=prompt.version)
        if step == "act":
            self.n += 1
            reply = ({"reflection": "more", "action": {"tool": "corpus_search",
                      "args": {"query": f"protein schedule item {self.n}", "regulation": None}}} if self.busy
                     else {"reflection": "enough", "action": {"tool": "finish", "args": {}}})
        elif step == "draft":
            def f(rid, p, status="met"):
                return {"requirement_id": rid, "requirement": rid, "status": status, "explanation": "ok",
                        "citations": [{"passage_id": p.passage_id, "quote": p.text}]}
            line = next(l for l in messages[1].content.splitlines() if l.startswith("Researched requirements"))
            self.ids = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip().startswith("LBL-")]
            reply = {"findings": [f("CLM-PROTEIN-SOURCE", AC)] + [f(r, LD) for r in self.ids],
                     "escalation_signals": []}  # a finding for every requirement the prompt lists
        else:  # support_check
            reply = {"checks": [{"requirement_id": rid, "label": self.support, "reason": "scripted"}
                                for rid in ["CLM-PROTEIN-SOURCE", *self.ids]]}
        return LLMResponse(text=json.dumps(reply), model_alias="scripted")


def pipeline(support, busy=False):
    llm, prompts, retr = ScriptedLLM(support, busy), FilePromptStore(), FakeRetriever()
    return LangGraphPipeline(guardrails=Guardrails(), classifier=StubClassifier(),
                             researcher=LangGraphResearcher(retr, llm, prompts),
                             verifier=AgentVerifier(retr, llm, prompts), router=RuleRouter())


LIMITS = dict(max_steps=25, max_tool_calls=15, max_wall_s=90, max_research_attempts=3)


def run_full(support, busy=False, **req):
    ctx = RunContext.new(limits=RunLimits(**LIMITS))
    result = pipeline(support, busy).run(sample_request(protein_g=30, **req), ctx)
    print(f"\nsupport={support} busy={busy} {req}: steps={len(ctx.steps)} tool_calls={ctx.tool_calls} "
          f"drafts={sum(s.name == 'draft' for s in ctx.steps)} route={result.routing.route.value}")
    return result, ctx


def test_a_verified_run_clears_in_about_fifteen_steps():
    """Demo #2 shape: every researched requirement has a cited finding, the verifier accepts, the label clears."""
    result, ctx = run_full("supported")
    assert result.complete and result.routing.route.value == "clear-for-print"
    assert len(ctx.steps) <= 16 and ctx.tool_calls <= 8


@pytest.mark.parametrize("busy", [False, True])
def test_worst_case_three_attempts_still_completes_inside_the_limits(busy):
    """The verifier rejects every attempt; the researcher runs three times (the last two narrower)."""
    result, ctx = run_full("unsupported", busy=busy)
    assert result.complete, result.routing.escalation_reason
    assert len(ctx.steps) <= 25 and ctx.tool_calls <= 15
    assert sum(s.name == "draft" for s in ctx.steps) == 3


def test_small_pack_adds_one_search_and_still_fits():
    result, ctx = run_full("unsupported", busy=True, package={"net_quantity": 50, "net_quantity_unit": "g",
                                                              "principal_display_panel_cm2": 40,
                                                              "total_surface_area_cm2": 120})
    assert result.complete and len(ctx.steps) <= 25 and ctx.tool_calls <= 15
