"""Retrieval recall@k against labelled queries (extras: recall@k on the eval set's supporting passages).

    python -m fssai_retrieval.evaluate --index data/index --queries data/corpus/eval/retrieval_queries.jsonl
    python -m fssai_retrieval.evaluate --index data/index --queries packages/eval/scenarios.jsonl    # EvalScenario lines

Each query line: {"id", "query", "relevant": [{"regulation", "clause_id"}], "tags"}. An EvalScenario line
uses its `description` as the query and its `supporting` passages as the relevant clauses.
A retrieved passage counts for a relevant clause if one contains the other ("5(3)" ~ "5(3)(c)").

Reported per configuration (dense, bm25, hybrid, hybrid + claim hints):
- hit@k     share of queries with at least one relevant clause in the top k
- recall@k  share of relevant clauses found in the top k, averaged over queries
- MRR       mean reciprocal rank of the first relevant clause (0 if none in the top 20)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .faiss_retriever import FaissRetriever
from .index import clause_contains

DEPTH = 20


@dataclass
class Query:
    id: str
    query: str
    relevant: list[tuple[str, str]]
    tags: list[str]


def load_queries(path: Path) -> list[Query]:
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if "query" in row:
            rel = [(r["regulation"], r["clause_id"]) for r in row["relevant"]]
            out.append(Query(row.get("id", str(n)), row["query"], rel, row.get("tags", [])))
        elif "supporting" in row:  # an EvalScenario (packages/eval/scenarios.jsonl)
            rel = [(s["regulation"], s["clause_id"]) for s in row["supporting"]]
            if rel:
                out.append(Query(row["scenario_id"], row["description"], rel, row.get("tags", [])))
    return out


def _is_relevant(regulation: str, clause_id: str, rel: tuple[str, str]) -> bool:
    return regulation == rel[0] and (clause_contains(rel[1], clause_id) or clause_contains(clause_id, rel[1]))


def evaluate(retriever: FaissRetriever, queries: list[Query], *, mode: str, hints: bool,
             ks: tuple[int, ...] = (1, 3, 5, 10)) -> dict:
    saved = retriever.hints
    if not hints:
        retriever.hints = None
    try:
        per_query = []
        for q in queries:
            ranked = retriever.rank(q.query, k=DEPTH, mode=mode)
            first = next((i for i, (c, _) in enumerate(ranked, start=1)
                          if any(_is_relevant(c.regulation, c.clause_id, r) for r in q.relevant)), None)
            found_at = {}
            for r in q.relevant:
                found_at[r] = next((i for i, (c, _) in enumerate(ranked, start=1)
                                    if _is_relevant(c.regulation, c.clause_id, r)), None)
            per_query.append({"id": q.id, "first": first, "tags": q.tags,
                              "found_at": {f"{reg}:{cid}": at for (reg, cid), at in found_at.items()},
                              "top3": [c.passage_id for c, _ in ranked[:3]]})
    finally:
        retriever.hints = saved
    n = len(per_query) or 1
    result = {"mode": mode, "hints": hints, "queries": len(per_query),
              "mrr": round(sum(1 / q["first"] for q in per_query if q["first"]) / n, 3)}
    for k in ks:
        result[f"hit@{k}"] = round(sum(1 for q in per_query if q["first"] and q["first"] <= k) / n, 3)
        result[f"recall@{k}"] = round(sum(
            sum(1 for v in q["found_at"].values() if v and v <= k) / len(q["found_at"]) for q in per_query) / n, 3)
    result["misses@5"] = [q["id"] for q in per_query if not q["first"] or q["first"] > 5]
    result["per_query"] = per_query
    return result


CONFIGS = (("dense", False), ("bm25", False), ("hybrid", False), ("hybrid", True))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m fssai_retrieval.evaluate", description=__doc__.split("\n")[0])
    p.add_argument("--index", default="data/index")
    p.add_argument("--queries", default="data/corpus/eval/retrieval_queries.jsonl")
    p.add_argument("--tag", default=None, help="only queries with this tag, e.g. section-4.1")
    p.add_argument("--json", default=None, help="also write the full results to this file")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    queries = load_queries(Path(args.queries))
    if args.tag:
        queries = [q for q in queries if args.tag in q.tags]
    retriever = FaissRetriever(Path(args.index), hints=True)
    results = []
    print(f"index {retriever.version} ({retriever.manifest.get('embedding_model')}), {len(queries)} queries")
    print(f"{'config':<16} {'hit@1':>6} {'hit@3':>6} {'hit@5':>6} {'hit@10':>7} {'recall@5':>9} {'MRR':>6}  misses@5")
    for mode, hints in CONFIGS:
        if mode != "bm25" and retriever.store is None:
            continue
        r = evaluate(retriever, queries, mode=mode, hints=hints)
        results.append(r)
        name = mode + (" + hints" if hints else "")
        print(f"{name:<16} {r['hit@1']:>6} {r['hit@3']:>6} {r['hit@5']:>6} {r['hit@10']:>7} {r['recall@5']:>9} "
              f"{r['mrr']:>6}  {', '.join(r['misses@5']) or '-'}")
    if args.json:
        Path(args.json).write_text(json.dumps({"index_version": retriever.version,
                                               "embedding_model": retriever.manifest.get("embedding_model"),
                                               "results": results}, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
