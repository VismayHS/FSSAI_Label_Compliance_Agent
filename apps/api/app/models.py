"""HTTP-only response shapes. Request bodies and run data are the contracts' own models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from fssai_contracts.schemas import (
    NOT_AN_APPROVAL, Classification, FieldError, Finding, GuardrailReport, LabelCheckRequest, Route,
    Routing, RunState, RunTotals, StepRecord, Verdict,
)


class RunAccepted(BaseModel):
    run_id: str
    status_url: str
    trace_url: str
    correlation_id: str


class RunRejected(BaseModel):
    errors: list[FieldError]
    quarantine_id: str | None = None
    correlation_id: str


class RateLimited(BaseModel):
    detail: str
    retry_after_s: float
    correlation_id: str


class Problem(BaseModel):
    detail: str
    correlation_id: str | None = None


class RunSummary(BaseModel):
    run_id: str
    state: RunState
    submitted_at: datetime
    updated_at: datetime
    product_name: str | None = None
    route: Route | None = None
    complete: bool | None = None


class AgentRollup(BaseModel):
    steps: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    errors: int = 0
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class RunTrace(BaseModel):
    """Everything needed to reconstruct a run from its id (D5): the request, every step in order with its
    inputs and outputs (queries, full passages, prompts, LLM text), prompt versions, per-step and per-agent
    latency and cost, the verification outcome and the route."""
    run_id: str
    correlation_id: str | None
    state: RunState
    submitted_at: datetime
    updated_at: datetime
    queue_wait_ms: float | None = None
    request: LabelCheckRequest | None = None
    complete: bool | None = None
    classification: Classification | None = None
    findings: list[Finding] = Field(default_factory=list)
    verdict: Verdict | None = None
    routing: Routing | None = None
    guardrails: list[GuardrailReport] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    totals: RunTotals | None = None
    agents: dict[str, AgentRollup] = Field(default_factory=dict)
    steps: list[StepRecord] = Field(default_factory=list)
    error: str | None = None
    jaeger_url: str | None = None  # this run's spans in Jaeger, when JAEGER_UI_URL is set
    notice: str = NOT_AN_APPROVAL
