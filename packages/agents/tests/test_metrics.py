"""Per-agent metrics (M3.3): counters move when a run finishes, and never break it."""
from prometheus_client import REGISTRY

from fssai_agents import metrics
from fssai_agents.graph import LangGraphPipeline
from fssai_contracts.conformance import sample_request
from fssai_contracts.context import RunContext


def value(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_a_run_updates_per_agent_metrics():
    before_runs = value("fssai_pipeline_runs_total", outcome="complete", route="regulatory-review") + \
        value("fssai_pipeline_runs_total", outcome="complete", route="clear-for-print") + \
        value("fssai_pipeline_runs_total", outcome="complete", route="revise-and-recheck")
    before_cls = value("fssai_agent_runs_total", agent="classifier", outcome="success")
    LangGraphPipeline.from_registry().run(sample_request(), RunContext.new())
    after_runs = sum(value("fssai_pipeline_runs_total", outcome="complete", route=r)
                     for r in ("regulatory-review", "clear-for-print", "revise-and-recheck"))
    assert after_runs == before_runs + 1
    assert value("fssai_agent_runs_total", agent="classifier", outcome="success") == before_cls + 1
    assert value("fssai_agent_steps_per_run_count", agent="classifier") >= 1


def test_retry_counter():
    before = value("fssai_agent_retries_total", agent="researcher")
    metrics.record_retry("researcher")
    assert value("fssai_agent_retries_total", agent="researcher") == before + 1
