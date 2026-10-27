"""The prompt-comparison helper (M3.2): table, verdict and report filling, on synthetic eval results."""
import json

from fssai_agents import compare


def results(version, **agg):
    base = {"scenarios": 30, "errors": 0, "provider_failures": 0, "route_accuracy": 0.6, "groundedness": 0.8,
            "faithfulness": 0.7, "hallucination_rate": 0.1, "unsafe_clear_rate": 0.0, "finding_accuracy": 0.5,
            "mean_tool_calls": 9.0, "mean_llm_calls": 6.0, "mean_cost_usd": 0.01, "citation_resolution": 0.9}
    base.update(agg)
    row = {"scenario_id": "s41-a", "tags": ["section-4.1"], "error": None, "provider_failed": False,
           "expected_findings": {"CLM-PROTEIN-SOURCE": {"got": "cannot_determine" if version == "1.1.0" else None}}}
    return {"tag": f"researcher-{version}", "created_at": "2026-10-28T00:00:00", "judge": "reference", "git_sha": "abc",
            "aggregate": base, "scenarios": [row]}


def test_a_safety_metric_decides_on_its_own():
    winner, reasons = compare.verdict(results("1.0.0", unsafe_clear_rate=0.1), results("1.1.0", route_accuracy=0.3))
    assert winner == "1.1.0" and "unsafe_clear_rate" in reasons[0]


def test_correctness_decides_when_safety_is_equal():
    winner, _ = compare.verdict(results("1.0.0"), results("1.1.0", route_accuracy=0.7, groundedness=0.9))
    assert winner == "1.1.0"
    winner, _ = compare.verdict(results("1.0.0", route_accuracy=0.8), results("1.1.0", route_accuracy=0.5))
    assert winner == "1.0.0"


def test_identical_runs_are_a_tie():
    assert compare.verdict(results("1.0.0"), results("1.1.0"))[0] == "tie"


def test_table_has_the_four_report_rows_with_differences():
    t = compare.table(results("1.0.0"), results("1.1.0", route_accuracy=0.7, mean_tool_calls=8.0))
    assert "| Route accuracy | 0.60 | 0.70 | +0.10 |" in t
    assert "| Mean tool calls per run | 9.00 | 8.00 | -1.00 |" in t
    assert "| Section 4.1 case reaches FSS-AC-2018 | 0.00 | 1.00 | +1.00 |" in t
    assert "| Groundedness / faithfulness | 0.80 / 0.70 | 0.80 / 0.70 | +0.00 / +0.00 |" in t


def test_report_todo_rows_are_replaced():
    text = (compare.REPORT).read_text(encoding="utf-8")
    before, after = results("1.0.0"), results("1.1.0", route_accuracy=0.7)
    winner, reasons = compare.verdict(before, after)
    out = compare.fill_report(text, before, after, winner, reasons)
    assert "| Route accuracy | 0.60 | 0.70 | +0.10 |" in out and "Result: researcher 1.1.0 was better" in out
    assert "TODO | TODO" not in out.split("## 5.")[1].split("## 6.")[0]


def test_decision_record_names_both_files_and_the_verdict():
    before, after = results("1.0.0"), results("1.1.0", route_accuracy=0.7)
    md = compare.decision_record(before, after, *compare.verdict(before, after))
    assert "researcher-1.0.0.json" in md and "researcher-1.1.0.json" in md and "Verdict: **1.1.0**" in md


def test_missing_results_say_what_to_run(tmp_path):
    try:
        compare.load("1.0.0", tmp_path)
    except FileNotFoundError as exc:
        assert "compare run" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_load_reads_a_results_file(tmp_path):
    (tmp_path / "researcher-1.0.0.json").write_text(json.dumps(results("1.0.0")), encoding="utf-8")
    assert compare.load("1.0.0", tmp_path)["tag"] == "researcher-1.0.0"
