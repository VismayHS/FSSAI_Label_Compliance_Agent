"""The runner, results files, compare and the regression gate, on the contracts' reference pipeline."""
import json

import pytest

from fssai_contracts.pipeline import ReferencePipeline
from fssai_eval.__main__ import load_env_file, main
from fssai_eval.judges import ReferenceJudge
from fssai_eval.runner import compare, load_scenarios, regression_gate, run_eval, summary_table, write_results

SCENARIOS = "packages/eval/scenarios.jsonl"


@pytest.fixture(autouse=True)
def cereals(monkeypatch):
    monkeypatch.setenv("CORPUS_CATEGORIES", "breakfast-cereals")


def test_the_eval_set_loads_and_is_large_enough():
    s = load_scenarios(SCENARIOS)
    assert len(s) >= 25 and len({x.scenario_id for x in s}) == len(s)
    tags = {t for x in s for t in x.tags}
    assert {"section-4.1", "injection", "out-of-scope", "exemption", "conflict", "trap", "no-condition"} <= tags
    assert sum("trap" in x.tags for x in s) >= 2
    assert all(x.supporting for x in s if "out-of-scope" not in x.tags and "injection" not in x.tags)


def test_run_eval_scores_every_scenario(tmp_path):
    scenarios = load_scenarios(SCENARIOS)[:6]
    res = run_eval(scenarios, "t", judge=ReferenceJudge(), pipeline=ReferencePipeline.from_registry())
    assert res["aggregate"]["scenarios"] == 6 and res["aggregate"]["errors"] == 0
    assert set(res["definitions"]) >= {"groundedness", "context_relevance", "faithfulness", "hallucination_rate"}
    assert not any("KEY" in k or "URL" in k for k in res["config"]), "no secrets in results files (D4)"
    path = write_results(res, tmp_path)
    assert json.loads(path.read_text())["tag"] == "t" and "route_accuracy" in summary_table(res)


def test_a_crashing_pipeline_is_an_error_row_not_a_crash():
    class Boom:
        def run(self, request, ctx):
            raise RuntimeError("kaput")
    res = run_eval(load_scenarios(SCENARIOS)[:2], "boom", judge=ReferenceJudge(), pipeline=Boom())
    assert res["aggregate"]["errors"] == 2 and "kaput" in res["scenarios"][0]["error"]


def _res(tag, **agg):
    base = {"hallucination_rate": 0.1, "route_accuracy": 0.8, "unsafe_clear_rate": 0.0, "errors": 0}
    return {"tag": tag, "aggregate": {**base, **agg}, "scenarios": [
        {"scenario_id": "a", "route": "clear-for-print", "expected_route": "clear-for-print"}]}


def test_compare_shows_deltas_and_direction():
    out = compare(_res("before"), _res("after", hallucination_rate=0.0, route_accuracy=0.9))
    assert "-0.100 better" in out and "+0.100 better" in out


def test_regression_gate():
    assert regression_gate(_res("a"), _res("b")) == []
    assert "hallucination" in regression_gate(_res("a"), _res("b", hallucination_rate=0.2))[0]
    assert "route accuracy" in regression_gate(_res("a"), _res("b", route_accuracy=0.7))[0]
    assert "unsafe clear" in regression_gate(_res("a"), _res("b", unsafe_clear_rate=0.1))[0]
    assert regression_gate(_res("a", unsafe_clear_rate=0.1), _res("b", unsafe_clear_rate=0.1)) == []


def test_cli_run_compare_gate(tmp_path, capsys):
    common = ["--env-file", "", "run", "--scenarios", SCENARIOS, "--only", "s41-protein-clearly-above,fibre-source-pass",
              "--out-dir", str(tmp_path), "--quiet"]
    assert main([*common, "--tag", "a"]) == 0 and main([*common, "--tag", "b"]) == 0
    assert main(["--env-file", "", "compare", "a", "b", "--out-dir", str(tmp_path)]) == 0
    assert main(["--env-file", "", "gate", "--baseline", "a", "--candidate", "b", "--out-dir", str(tmp_path)]) == 0
    assert "eval gate: passed" in capsys.readouterr().out


def test_env_file_does_not_override_the_shell(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FSSAI_T1=from-file   # comment\nFSSAI_T2=from-file\n# FSSAI_T3=no\n")
    monkeypatch.setenv("FSSAI_T2", "from-shell")
    monkeypatch.delenv("FSSAI_T1", raising=False)
    assert load_env_file(env) == 1
    import os
    assert os.environ["FSSAI_T1"] == "from-file" and os.environ["FSSAI_T2"] == "from-shell"
    monkeypatch.delenv("FSSAI_T1")


# ---------------------------------------------------------------- free-tier pacing (Groq: 8k tokens/min, 1k requests/day)

class Incomplete:
    """A pipeline whose provider gives out on chosen scenarios, like a rate-limited free tier."""

    def __init__(self, failing=()):
        from fssai_contracts.pipeline import ReferencePipeline
        self.inner, self.failing, self.calls = ReferencePipeline.from_registry(), set(failing), []

    def run(self, request, ctx):
        from fssai_contracts.schemas import Route, RunResult, Routing
        self.calls.append(request.label.product_name)
        if request.label.product_name in self.failing:
            return RunResult(run_id=ctx.run_id, correlation_id=ctx.correlation_id, complete=False,
                             routing=Routing(route=Route.REGULATORY_REVIEW, reason="Run did not complete.",
                                             escalation_reason="ProviderUnavailable: 429 rate limited"))
        return self.inner.run(request, ctx)


def test_pause_between_scenarios(monkeypatch):
    import fssai_eval.runner as runner
    slept = []
    monkeypatch.setattr(runner.time, "sleep", slept.append)
    run_eval(load_scenarios(SCENARIOS)[:3], "p", judge=ReferenceJudge(), pipeline=ReferencePipeline.from_registry(),
             pause_s=60)
    assert slept == [60, 60], "a pause between scenarios, none after the last"


def test_provider_failures_are_marked_and_resume_reruns_only_them():
    scenarios = load_scenarios(SCENARIOS)[:3]
    flaky = scenarios[1].request.label.product_name
    first = run_eval(scenarios, "r", judge=ReferenceJudge(), pipeline=Incomplete(failing={flaky}))
    rows = {r["scenario_id"]: r for r in first["scenarios"]}
    assert rows[scenarios[1].scenario_id]["provider_failed"] is True
    assert first["aggregate"]["provider_failures"] == 1
    assert first["aggregate"]["scenarios"] == 2, "a provider failure is not scored as an escalation"

    again = Incomplete()
    second = run_eval(scenarios, "r", judge=ReferenceJudge(), pipeline=again, resume=first)
    assert again.calls == [flaky], "only the scenario the provider failed is run again"
    assert second["aggregate"]["provider_failures"] == 0 and len(second["scenarios"]) == 3


def test_checkpoint_after_every_scenario():
    seen = []
    run_eval(load_scenarios(SCENARIOS)[:2], "c", judge=ReferenceJudge(), pipeline=ReferencePipeline.from_registry(),
             checkpoint=lambda res: seen.append(len(res["scenarios"])))
    assert seen == [1, 2]
