"""Shared test settings for fssai_agents.

The researcher reads each mandatory declaration by clause id (decision 310), so a run needs the step and tool-call
budget `.env.example` sets: RUN_MAX_STEPS=30, RUN_MAX_TOOL_CALLS=18. Tests that build a RunContext without explicit
limits use these."""
import pytest


@pytest.fixture(autouse=True)
def _run_limits(monkeypatch):
    monkeypatch.setenv("RUN_MAX_STEPS", "30")
    monkeypatch.setenv("RUN_MAX_TOOL_CALLS", "18")
