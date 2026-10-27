"""Slow, opt-in: the section 4.1 request end to end through LangGraphPipeline with a real LLM and the real index.

Skipped unless both seams are switched on, so a plain `pytest` never spends tokens or needs an index:

    IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever  INDEX_DIR=<index built by fssai_ingest>
    IMPL_LLM=fssai_agents.dev_llm:UADevLLMClient  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...
    IMPL_PROMPTS=fssai_prompts.store:FilePromptStore  CORPUS_CATEGORIES=breakfast-cereals

It asserts things that must hold for any sensible model: the run ends in a defined state, every citation
resolves to text retrieved in this run, a clear-for-print route is never given on unsupported or
undetermined findings, and the Claims regulation was reached (the point of section 4.1).
"""
import os

import pytest

from fssai_agents.classifier import LLMClassifier
from fssai_agents.graph import LangGraphPipeline
from fssai_agents.researcher import LangGraphResearcher
from fssai_contracts.conformance import sample_request
from fssai_contracts.context import RunContext
from fssai_contracts.registry import build
from fssai_contracts.schemas import FindingStatus, Route

pytestmark = pytest.mark.skipif(
    not (os.environ.get("IMPL_RETRIEVER") and os.environ.get("IMPL_LLM")),
    reason="opt-in: set IMPL_RETRIEVER (+INDEX_DIR) and IMPL_LLM (+LLM_*) to run against the real stack")


def test_section_4_1_end_to_end():
    pipeline = LangGraphPipeline(
        guardrails=build("guardrails"), classifier=LLMClassifier.from_registry(),
        researcher=LangGraphResearcher.from_registry(), verifier=build("verifier"), router=build("router"))
    ctx = RunContext.new()
    result = pipeline.run(sample_request(), ctx)  # claim "Source of protein", protein 12 g per 100 g

    assert result.notice and result.steps
    assert result.routing.route in set(Route)
    if not result.complete:
        assert result.routing.route == Route.REGULATORY_REVIEW  # an incomplete run is never a confident answer

    retrieved = {p["passage_id"]: p for s in ctx.steps if s.kind == "tool" for p in s.output.get("passages", [])}
    assert retrieved, "the researcher retrieved nothing"
    for f in result.findings:
        for c in f.citations:
            assert c.passage_id in retrieved and c.quote in retrieved[c.passage_id]["text"], f"{f.requirement_id}: unresolved citation"
    assert any(p["regulation"] == "FSS-AC-2018" for p in retrieved.values()), "the Claims regulation was never reached"

    if result.routing.route == Route.CLEAR_FOR_PRINT:
        assert result.findings and all(f.status in (FindingStatus.MET, FindingStatus.NOT_APPLICABLE) and f.citations
                                       for f in result.findings)
    print("\nroute:", result.routing.route.value, "| complete:", result.complete,
          "| steps:", len(result.steps), "| tool calls:", ctx.tool_calls)
    for f in result.findings:
        print(" ", f.requirement_id, f.status.value, [c.passage_id for c in f.citations])
