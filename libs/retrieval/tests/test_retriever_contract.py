"""FaissRetriever keeps the retriever contract (fssai_contracts.conformance.check_retriever)."""
from fssai_contracts.conformance import check_retriever
from fssai_retrieval.faiss_retriever import FaissRetriever


def test_conforms(index_dir, monkeypatch):
    monkeypatch.setenv("INDEX_DIR", str(index_dir))
    monkeypatch.setenv("CACHE_ENABLED", "0")
    check_retriever(FaissRetriever.from_registry())


def test_conforms_in_every_mode(index_dir):
    for mode in ("hybrid", "dense", "bm25"):
        check_retriever(FaissRetriever(index_dir, mode=mode))
