"""The eval tools: the published JSON Schema is current, and the scenario checker catches fabricated quotes."""
import json
import subprocess
import sys
from pathlib import Path

from fssai_contracts.schemas import EvalScenario

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "eval" / "tools"))
import check_scenarios  # noqa: E402
import export_schema  # noqa: E402


def test_published_schema_is_up_to_date():
    assert export_schema.main(["--check"]) == 0, "run packages/eval/tools/export_schema.py and commit docs/data-contract.schema.json"


def test_schema_carries_the_gate_constraints():
    s = export_schema.build()
    assert s["$defs"]["NutritionPanel"]["properties"]["protein_g"]["maximum"] == 100
    assert s["additionalProperties"] is False and "XF-08" in s["x-cross-field-rules"]


PASSAGES = [{"passage_id": "FSS-LD-2020:5(14)", "regulation": "FSS-LD-2020", "clause_id": "5(14)",
             "text": "(14) Declaration regarding Food allergen: The following foods and ingredients which are known "
                     "to cause allergy shall be declared separately as Contains"},
            {"passage_id": "FSS-LD-2020:5(3)(c)+2", "regulation": "FSS-LD-2020", "clause_id": "5(3)(c)",
             "text": "However, nutritional information shall be required in the above -mentioned products if a "
                     "nutrition or health claim is made on the label."}]


def test_quote_check():
    assert check_scenarios.check_quote(PASSAGES, "FSS-LD-2020", "5(14)", "shall be declared separately") is None
    assert check_scenarios.check_quote(PASSAGES, "FSS-LD-2020", "5(3)(c)", "if a nutrition or health claim") is None
    assert "not verbatim" in check_scenarios.check_quote(PASSAGES, "FSS-LD-2020", "5(14)", "allergens must be listed")
    assert "is in FSS-LD-2020:5(14)" in check_scenarios.check_quote(PASSAGES, "FSS-LD-2020", "5(3)(c)", "known to cause allergy")
    assert "no clause" in check_scenarios.check_quote(PASSAGES, "FSS-LD-2020", "99(1)", "x")


def test_checker_on_the_real_eval_set_with_a_mini_index(tmp_path):
    """Every scenario's request passes the gate (quotes are checked separately against the real index in CI)."""
    problems = check_scenarios.check(ROOT / "packages" / "eval" / "scenarios.jsonl", None)
    assert problems == []


def test_checker_flags_a_fabricated_quote(tmp_path):
    line = json.loads((ROOT / "packages" / "eval" / "scenarios.jsonl").read_text().splitlines()[0])
    line["supporting"] = [{"regulation": "FSS-LD-2020", "clause_id": "5(14)", "quote": "a made-up regulation sentence"}]
    (tmp_path / "s.jsonl").write_text(EvalScenario.model_validate(line).model_dump_json() + "\n")
    (tmp_path / "idx").mkdir()
    (tmp_path / "idx" / "passages.jsonl").write_text("".join(json.dumps(p) + "\n" for p in PASSAGES))
    problems = check_scenarios.check(tmp_path / "s.jsonl", tmp_path / "idx")
    assert len(problems) == 1 and "not verbatim" in problems[0]


def test_checker_cli_runs():
    out = subprocess.run([sys.executable, str(ROOT / "packages" / "eval" / "tools" / "check_scenarios.py")], capture_output=True,
                         text=True, cwd=ROOT, env={"PATH": "", "INDEX_DIR": ""})
    assert out.returncode == 0, out.stderr
