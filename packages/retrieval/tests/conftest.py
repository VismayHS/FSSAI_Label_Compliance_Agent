"""A real index built once per session from data/corpus/raw, with the offline hashing embedder.

Dense recall with the hashing embedder is lexical, not semantic; tests that need the real model are
opt-in (see test_retrieval_quality.py). Everything else (filters, lookups, caching, contract) is
model-independent and runs here in seconds.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "corpus" / "raw"


@pytest.fixture(scope="session")
def index_dir(tmp_path_factory) -> Path:
    if not any(CORPUS.glob("*.pdf")):
        pytest.skip("data/corpus/raw has no PDFs")
    build = pytest.importorskip("fssai_ingest.build", reason="fssai-ingest builds the test index")
    out = tmp_path_factory.mktemp("index")
    build.build_index(CORPUS, out, model_alias="hashing")
    return out
