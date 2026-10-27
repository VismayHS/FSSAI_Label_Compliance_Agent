"""Retrieval quality with the real embedding model (opt-in: it needs the model in the local HF cache).

    FSSAI_QUALITY_INDEX=data/index pytest packages/retrieval/tests/test_retrieval_quality.py

FSSAI_QUALITY_INDEX points at an index built with the real EMBEDDING_MODEL (python -m fssai_ingest
build). The thresholds are the measured values in docs/report/retrieval-and-performance.md, rounded
down, so a chunker or retrieval change that loses recall fails here.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fssai_retrieval.evaluate import evaluate, load_queries
from fssai_retrieval.faiss_retriever import FaissRetriever

ROOT = Path(__file__).resolve().parents[3]
QUERIES = ROOT / "data" / "corpus" / "eval" / "retrieval_queries.jsonl"
INDEX = os.environ.get("FSSAI_QUALITY_INDEX", "")

pytestmark = pytest.mark.skipif(not INDEX, reason="set FSSAI_QUALITY_INDEX to an index built with the real model")


@pytest.fixture(scope="module")
def retriever() -> FaissRetriever:
    r = FaissRetriever(Path(INDEX))
    if r.store is None or str(r.manifest.get("embedding_model", "")).startswith("hashing"):
        pytest.skip("needs an index built with a real sentence-transformers model")
    return r


def test_hybrid_finds_every_section_41_phrasing_without_hints(retriever):
    queries = [q for q in load_queries(QUERIES) if "section-4.1" in q.tags]
    result = evaluate(retriever, queries, mode="hybrid", hints=False)
    assert result["hit@5"] == 1.0, result["misses@5"]


def test_hybrid_beats_dense_alone(retriever):
    queries = load_queries(QUERIES)
    dense = evaluate(retriever, queries, mode="dense", hints=False)
    hybrid = evaluate(retriever, queries, mode="hybrid", hints=False)
    assert hybrid["hit@5"] > dense["hit@5"] and hybrid["mrr"] >= dense["mrr"]


def test_hybrid_with_hints_meets_the_measured_bar(retriever):
    result = evaluate(retriever, load_queries(QUERIES), mode="hybrid", hints=True)
    assert result["hit@5"] >= 0.95 and result["mrr"] >= 0.8, result["misses@5"]
