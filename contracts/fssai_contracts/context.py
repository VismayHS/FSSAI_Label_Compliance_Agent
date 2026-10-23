"""Per-run context: identity, loop bounds (A1), the step trace (D5) and structured events.

Who records what:
- LLMClient implementations record their own "llm" steps (they know tokens and cost).
- The agent layer records "tool" steps when it calls a tool.
- Everything else records its own step kind.
Call `check_budget()` before every step; it raises BudgetExceeded when a bound is hit.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field

from .schemas import RunTotals, StepRecord, utcnow

log = logging.getLogger("fssai")


class BudgetExceeded(RuntimeError):
    """A loop bound (steps, tool calls or wall-clock) was hit."""


def _env_num(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


@dataclass
class RunLimits:
    max_steps: int = 25
    max_tool_calls: int = 15
    max_wall_s: float = 90.0
    max_research_attempts: int = 3

    @classmethod
    def from_env(cls) -> RunLimits:
        return cls(
            max_steps=int(_env_num("RUN_MAX_STEPS", cls.max_steps)),
            max_tool_calls=int(_env_num("RUN_MAX_TOOL_CALLS", cls.max_tool_calls)),
            max_wall_s=_env_num("RUN_MAX_WALL_S", cls.max_wall_s),
            max_research_attempts=int(_env_num("RUN_MAX_RESEARCH_ATTEMPTS", cls.max_research_attempts)),
        )


@dataclass
class RunContext:
    run_id: str
    correlation_id: str
    limits: RunLimits = field(default_factory=RunLimits.from_env)
    started: float = field(default_factory=time.monotonic)
    steps: list[StepRecord] = field(default_factory=list)
    prompt_versions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls, run_id: str | None = None, correlation_id: str | None = None, **kw) -> RunContext:
        run_id = run_id or uuid.uuid4().hex
        return cls(run_id=run_id, correlation_id=correlation_id or run_id, **kw)

    # ---- bounds

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started

    def remaining_s(self) -> float:
        return max(0.0, self.limits.max_wall_s - self.elapsed_s())

    @property
    def tool_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "tool")

    def check_budget(self, *, tool_call: bool = False) -> None:
        if len(self.steps) >= self.limits.max_steps:
            raise BudgetExceeded(f"step limit {self.limits.max_steps} reached")
        if tool_call and self.tool_calls >= self.limits.max_tool_calls:
            raise BudgetExceeded(f"tool-call limit {self.limits.max_tool_calls} reached")
        if self.remaining_s() <= 0:
            raise BudgetExceeded(f"wall-clock limit {self.limits.max_wall_s}s reached")

    # ---- trace

    def record(self, *, agent: str, kind: str, name: str, latency_ms: float = 0.0, **fields) -> StepRecord:
        step = StepRecord(
            step_index=len(self.steps), agent=agent, kind=kind, name=name,
            started_at=utcnow(), latency_ms=latency_ms, **fields,
        )
        self.steps.append(step)
        if step.prompt_name and step.prompt_version:
            self.prompt_versions[step.prompt_name] = step.prompt_version
        self.event("step", agent=agent, kind=kind, name=name, step_index=step.step_index,
                   latency_ms=round(latency_ms, 1), cost_usd=step.cost_usd, error=step.error)
        return step

    def totals(self) -> RunTotals:
        return RunTotals(
            steps=len(self.steps),
            tool_calls=self.tool_calls,
            llm_calls=sum(1 for s in self.steps if s.kind == "llm"),
            prompt_tokens=sum(s.prompt_tokens for s in self.steps),
            completion_tokens=sum(s.completion_tokens for s in self.steps),
            cost_usd=round(sum(s.cost_usd for s in self.steps), 6),
            latency_ms=round(self.elapsed_s() * 1000, 1),
        )

    # ---- structured logging (D5). The format may change; call sites should not.

    def event(self, event: str, **fields) -> None:
        log.info(json.dumps({
            "event": event, "run_id": self.run_id, "correlation_id": self.correlation_id,
            "ts": utcnow().isoformat(), **fields,
        }, default=str))
