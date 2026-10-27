"""Structured-output validation with one repair attempt, and its metrics (M3 extra)."""
import json

import pytest
from prometheus_client import REGISTRY

from fssai_agents.structured import ask_structured, parse_json
from fssai_contracts.context import RunContext, RunLimits
from fssai_contracts.schemas import LLMMessage, LLMResponse


class Seq:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        self.calls.append((step, messages))
        ctx.record(agent=agent, kind="llm", name=step)
        return LLMResponse(text=self.replies.pop(0), model_alias="seq")


def count(step, outcome):
    return REGISTRY.get_sample_value("fssai_structured_output_total", {"agent": "t", "step": step, "outcome": outcome}) or 0.0


MSGS = [LLMMessage(role="system", content="s"), LLMMessage(role="user", content="u")]
NEEDS_X = lambda d: None if "x" in d else "it has no x"  # noqa: E731


@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}), ('```json\n{"a": 1}\n```', {"a": 1}), ("```\n{\"a\": 1}\n```", {"a": 1}),
    ("[1, 2]", None), ("nope", None), ("", None), (None, None)])
def test_parse_json(text, expected):
    assert parse_json(text) == expected


def test_a_valid_first_reply_costs_one_call():
    before = count("s1", "valid")
    llm = Seq('{"x": 1}')
    data, _ = ask_structured(llm, MSGS, RunContext.new(), agent="t", step="s1", prompt=None, check=NEEDS_X)
    assert data == {"x": 1} and len(llm.calls) == 1 and count("s1", "valid") == before + 1


def test_a_bad_reply_is_repaired_once_with_the_model_shown_its_own_reply_and_the_problem():
    before = count("s2", "repaired")
    llm = Seq("prose", '{"x": 2}')
    data, _ = ask_structured(llm, MSGS, RunContext.new(), agent="t", step="s2", prompt=None, check=NEEDS_X)
    assert data == {"x": 2} and [c[0] for c in llm.calls] == ["s2", "s2_repair"]
    repair = llm.calls[1][1]
    assert repair[-2].role == "assistant" and repair[-2].content == "prose" and "not a single JSON object" in repair[-1].content
    assert count("s2", "repaired") == before + 1


def test_a_reply_of_the_wrong_shape_is_repaired_and_the_check_names_the_problem():
    llm = Seq('{"y": 1}', '{"x": 3}')
    data, _ = ask_structured(llm, MSGS, RunContext.new(), agent="t", step="s3", prompt=None, check=NEEDS_X)
    assert data == {"x": 3} and "it has no x" in llm.calls[1][1][-1].content


def test_two_bad_replies_fail_after_exactly_one_repair():
    before = count("s4", "failed")
    llm = Seq("a", "b")
    data, text = ask_structured(llm, MSGS, RunContext.new(), agent="t", step="s4", prompt=None, check=NEEDS_X)
    assert data is None and text == "b" and len(llm.calls) == 2 and count("s4", "failed") == before + 1


def test_repair_off_asks_once_and_counts_skipped():
    before = count("s5", "skipped")
    llm = Seq("a")
    data, _ = ask_structured(llm, MSGS, RunContext.new(), agent="t", step="s5", prompt=None, repair=False)
    assert data is None and len(llm.calls) == 1 and count("s5", "skipped") == before + 1


def test_no_repair_when_the_step_budget_is_spent():
    ctx = RunContext.new(limits=RunLimits(max_steps=1))
    llm = Seq("a", '{"x": 1}')
    data, _ = ask_structured(llm, MSGS, ctx, agent="t", step="s6", prompt=None, check=NEEDS_X)
    assert data is None and len(llm.calls) == 1  # check_budget refused the second call
