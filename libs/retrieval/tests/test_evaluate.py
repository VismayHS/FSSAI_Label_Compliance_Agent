"""The recall@k evaluator and the labelled query set it reads."""
from __future__ import annotations

import json
from pathlib import Path

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Regulation
from fssai_retrieval.evaluate import evaluate, load_queries, main
from fssai_retrieval.faiss_retriever import FaissRetriever

QUERIES = Path(__file__).resolve().parents[3] / "corpus" / "eval" / "retrieval_queries.jsonl"


def test_every_labelled_clause_exists(index_dir):
    """A label pointing at a clause the corpus lacks would make recall meaningless."""
    r = FaissRetriever(index_dir)
    for q in load_queries(QUERIES):
        for reg, clause in q.relevant:
            assert r.get_clause(Regulation(reg), clause, RunContext.new()) is not None, f"{q.id}: {reg} {clause}"


def test_metrics_are_well_formed(index_dir):
    queries = load_queries(QUERIES)
    result = evaluate(FaissRetriever(index_dir), queries, mode="hybrid", hints=True)
    assert result["queries"] == len(queries) >= 20
    assert 0 <= result["hit@1"] <= result["hit@5"] <= result["hit@10"] <= 1
    assert 0 <= result["mrr"] <= 1


def test_reads_eval_scenarios_too(tmp_path):
    line = {"scenario_id": "S1", "description": "source of protein", "tags": ["section-4.1"],
            "supporting": [{"regulation": "FSS-AC-2018", "clause_id": "Schedule I, item 11", "quote": "x"}]}
    path = tmp_path / "scenarios.jsonl"
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    (q,) = load_queries(path)
    assert q.query == "source of protein" and q.relevant == [("FSS-AC-2018", "Schedule I, item 11")]


def test_cli_writes_json(index_dir, tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["--index", str(index_dir), "--queries", str(QUERIES), "--tag", "section-4.1", "--json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {r["mode"] for r in data["results"]} == {"dense", "bm25", "hybrid"}
    assert "hybrid + hints" in capsys.readouterr().out
