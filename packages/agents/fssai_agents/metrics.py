"""Per-agent metrics (docs/contexts/Namith.md M3.3; A6), labelled by agent.

They are derived from the run's own step trace when a run finishes, so the numbers on the dashboard are the same ones
a trace shows. They live in the default prometheus_client registry of whatever process runs the pipeline (the worker,
which already serves /metrics on WORKER_METRICS_PORT), so Nishkal's Prometheus scrapes them with no extra wiring.

  fssai_agent_runs_total{agent,outcome}      outcome = success | failure ("task success rate" = success / all)
  fssai_agent_steps_per_run{agent}           steps one agent took in a run
  fssai_agent_tool_calls_per_run{agent}      tool calls one agent made in a run
  fssai_agent_step_seconds{agent,kind}       latency of each step
  fssai_agent_retries_total{agent}           research retries asked for by the verifier
  fssai_pipeline_run_seconds                 end-to-end latency of a pipeline run (sum of step latencies' wall clock)
  fssai_pipeline_runs_total{outcome,route}   complete runs by route; outcome = complete | incomplete
"""
from __future__ import annotations

from collections import defaultdict

from prometheus_client import Counter, Histogram

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import RunResult

AGENT_RUNS = Counter("fssai_agent_runs_total", "Runs in which an agent took part", ["agent", "outcome"])
AGENT_STEPS = Histogram("fssai_agent_steps_per_run", "Steps an agent took in one run", ["agent"],
                        buckets=(1, 2, 3, 5, 8, 13, 21, 34, 55))
AGENT_TOOL_CALLS = Histogram("fssai_agent_tool_calls_per_run", "Tool calls an agent made in one run", ["agent"],
                             buckets=(0, 1, 2, 3, 5, 8, 12, 20))
STEP_SECONDS = Histogram("fssai_agent_step_seconds", "Latency of one agent step", ["agent", "kind"],
                         buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30))
AGENT_RETRIES = Counter("fssai_agent_retries_total", "Retries an agent was asked to make", ["agent"])
PIPELINE_SECONDS = Histogram("fssai_pipeline_run_seconds", "End-to-end latency of a pipeline run",
                             buckets=(0.5, 1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180))
PIPELINE_RUNS = Counter("fssai_pipeline_runs_total", "Pipeline runs", ["outcome", "route"])


def record_retry(agent: str = "researcher") -> None:
    AGENT_RETRIES.labels(agent=agent).inc()


def observe_run(result: RunResult, ctx: RunContext) -> None:
    """Called once per run, after the result is built. Never raises: metrics must not break a run."""
    try:
        steps: dict[str, list] = defaultdict(list)
        for s in ctx.steps:
            steps[s.agent].append(s)
            STEP_SECONDS.labels(agent=s.agent, kind=s.kind).observe(max(s.latency_ms, 0.0) / 1000.0)
        for agent, recorded in steps.items():
            failed = any(s.error for s in recorded) or not result.complete
            AGENT_RUNS.labels(agent=agent, outcome="failure" if failed else "success").inc()
            AGENT_STEPS.labels(agent=agent).observe(len(recorded))
            AGENT_TOOL_CALLS.labels(agent=agent).observe(sum(1 for s in recorded if s.kind == "tool"))
        PIPELINE_SECONDS.observe(max(result.totals.latency_ms, 0.0) / 1000.0)
        PIPELINE_RUNS.labels(outcome="complete" if result.complete else "incomplete",
                             route=result.routing.route.value).inc()
    except Exception:  # noqa: BLE001
        pass
