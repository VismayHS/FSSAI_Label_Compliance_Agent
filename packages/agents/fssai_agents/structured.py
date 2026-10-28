"""Structured-output validation with one repair attempt, and metrics (M3 extra; A6).

A model that was asked for JSON sometimes answers in prose, in a fence, or with the wrong shape. `ask_structured` calls
the LLM, parses and checks the reply, and, if it is unusable and repair is allowed, asks once more showing the model its
own reply and what was wrong. The repair is an LLM step like any other, so `ctx.check_budget()` runs before it and the
run's step limit still applies. Outcomes are counted in `fssai_structured_output_total{agent,step,outcome}`:

    valid     the first reply was usable
    repaired  the first reply was not, the second was
    failed    still unusable (the caller falls back or escalates)
    skipped   unusable and repair was off or the budget was spent
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

from prometheus_client import Counter

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.schemas import LLMMessage

STRUCTURED = Counter("fssai_structured_output_total", "LLM replies that had to be a JSON object, by outcome",
                     ["agent", "step", "outcome"])

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_json(text: str) -> dict | None:
    """The reply as a JSON object, tolerating a surrounding code fence; None if it is anything else."""
    text = (text or "").strip()
    fenced = _FENCE.match(text)
    try:
        data = json.loads(fenced.group(1) if fenced else text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _problem(text: str, check: Callable[[dict], str | None]) -> tuple[dict | None, str | None]:
    data = parse_json(text)
    if data is None:
        return None, "it was not a single JSON object"
    return (data, None) if (why := check(data)) is None else (None, why)


def ask_structured(llm, messages: list[LLMMessage], ctx: RunContext, *, agent: str, step: str, prompt,
                   check: Callable[[dict], str | None] = lambda _d: None, repair: bool = True,
                   ) -> tuple[dict | None, str]:
    """Returns (data or None, the last reply's text). `check` returns None if the data is usable, else what is wrong."""
    reply = llm.complete(messages, ctx, agent=agent, step=step, prompt=prompt, json_mode=True)
    data, why = _problem(reply.text, check)
    if data is not None:
        STRUCTURED.labels(agent=agent, step=step, outcome="valid").inc()
        return data, reply.text
    if not repair:
        STRUCTURED.labels(agent=agent, step=step, outcome="skipped").inc()
        return None, reply.text
    try:
        ctx.check_budget()
    except BudgetExceeded:
        STRUCTURED.labels(agent=agent, step=step, outcome="skipped").inc()
        return None, reply.text
    again = [*messages, LLMMessage(role="assistant", content=reply.text[:2000]),
             LLMMessage(role="user", content=f"That reply was not usable: {why}. Reply with only the JSON object "
                                             "described in the instructions, nothing else.")]
    fixed = llm.complete(again, ctx, agent=agent, step=f"{step}_repair", prompt=prompt, json_mode=True)
    data, _ = _problem(fixed.text, check)
    STRUCTURED.labels(agent=agent, step=step, outcome="repaired" if data is not None else "failed").inc()
    return data, fixed.text
