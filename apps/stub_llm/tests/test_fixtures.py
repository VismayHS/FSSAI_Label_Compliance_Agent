"""Every prompt the agents use has a stub fixture of the right shape (load tests take the same parse path)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fssai_stub_llm.app import FIXTURES

REQUIRED_KEYS = {
    "classifier": {"category", "claims", "rationale"},
    "guardrail_judge": {"flagged_fields", "reason"},
    "researcher": {"reflection", "action"},
    "researcher_draft": {"findings", "escalation_signals"},
    "verifier_support": {"checks"},
}


@pytest.mark.parametrize("name", sorted(REQUIRED_KEYS))
def test_prompt_fixture_has_the_reply_shape_its_prompt_asks_for(name):
    body = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert REQUIRED_KEYS[name] <= body.keys()


def test_researcher_fixture_finishes_so_load_runs_take_one_step():
    body = json.loads((FIXTURES / "researcher.json").read_text(encoding="utf-8"))
    assert body["action"]["tool"] == "finish"


def test_every_fixture_is_valid_json_and_the_default_is_still_there():
    paths = list(Path(FIXTURES).glob("*.json"))
    assert FIXTURES.joinpath("_default.json") in paths
    for path in paths:
        json.loads(path.read_text(encoding="utf-8"))
