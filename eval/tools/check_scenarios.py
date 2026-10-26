"""Check eval/scenarios.jsonl before anyone trusts a metric computed on it (L3).

    <venv-python> eval/tools/check_scenarios.py [--scenarios eval/scenarios.jsonl] [--index $INDEX_DIR]

For every scenario:
- it parses as an EvalScenario and its scenario_id is unique;
- its request passes the real gate (fssai_gate): an eval request that the API would reject measures nothing;
- each supporting quote is verbatim text of the clause it names, in the corpus as the indexer extracts it
  (passages.jsonl in an index built by `python -m fssai_ingest build`). This guards against the worst failure
  of an eval set: a "supporting passage" that is not real regulation text.
Exit 1 on any problem. Without an index, the quote check is skipped with a warning.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from fssai_contracts.schemas import EvalScenario

ROOT = Path(__file__).resolve().parents[2]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_passages(index_dir: Path) -> list[dict]:
    path = index_dir / "passages.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _clause_matches(p: dict, regulation: str, clause_id: str) -> bool:
    if p["regulation"] != regulation:
        return False
    base = p["passage_id"].split(":", 1)[1]
    return p["clause_id"] == clause_id or re.split(r"[~+#]", base, maxsplit=1)[0] == clause_id


def check_quote(passages: list[dict], regulation: str, clause_id: str, quote: str) -> str | None:
    """None if the quote is verbatim text of that clause; else what is wrong."""
    q = _norm(quote)
    in_clause = [p for p in passages if _clause_matches(p, regulation, clause_id)]
    if not in_clause:
        return f"{regulation} has no clause '{clause_id}' in the index"
    if any(q in _norm(p["text"]) for p in in_clause):
        return None
    elsewhere = [p["passage_id"] for p in passages if p["regulation"] == regulation and q in _norm(p["text"])]
    if elsewhere:
        return f"quote is in {elsewhere[0]}, not in clause '{clause_id}'"
    return f"quote is not verbatim text of {regulation} {clause_id}"


def check(scenarios_path: Path, index_dir: Path | None) -> list[str]:
    from fssai_gate.gate import RequestGate

    problems: list[str] = []
    lines = [ln for ln in scenarios_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    scenarios: list[EvalScenario] = []
    for n, line in enumerate(lines, 1):
        try:
            scenarios.append(EvalScenario.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 - report every bad line, not just the first
            problems.append(f"line {n}: not an EvalScenario: {exc}")
    dup = [k for k, v in Counter(s.scenario_id for s in scenarios).items() if v > 1]
    problems += [f"duplicate scenario_id {d}" for d in dup]

    gate = RequestGate()
    for s in scenarios:
        d = gate.check(s.request.model_dump(mode="json"), "eval-check")
        if not d.accepted:
            problems.append(f"{s.scenario_id}: the gate rejects its request: "
                            + "; ".join(f"{e.loc} {e.code}" for e in d.errors))

    if index_dir is None or not (index_dir / "passages.jsonl").exists():
        print(f"warning: no index at {index_dir}; supporting quotes NOT checked against the corpus", file=sys.stderr)
        return problems
    passages = load_passages(index_dir)
    for s in scenarios:
        for sp in s.supporting:
            why = check_quote(passages, sp.regulation.value, sp.clause_id, sp.quote)
            if why:
                problems.append(f"{s.scenario_id}: {why}: {sp.quote[:80]!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check the eval set: shape, gate, verbatim supporting quotes.")
    ap.add_argument("--scenarios", type=Path, default=ROOT / "eval" / "scenarios.jsonl")
    ap.add_argument("--index", type=Path, default=Path(os.environ["INDEX_DIR"]) if os.environ.get("INDEX_DIR") else None)
    args = ap.parse_args(argv)
    problems = check(args.scenarios, args.index)
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print(f"{args.scenarios}: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
