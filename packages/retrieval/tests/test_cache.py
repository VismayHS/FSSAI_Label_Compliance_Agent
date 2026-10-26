"""The retrieval cache (D7): hits on repeats, keyed by index version, never fails a search."""
from __future__ import annotations

import fakeredis
import pytest

from fssai_contracts.context import RunContext
from fssai_retrieval.cache import CACHE_EVENTS, RetrievalCache
from fssai_retrieval.faiss_retriever import FaissRetriever


def _count(cache: str, result: str, backend: str) -> float:
    return CACHE_EVENTS.labels(cache, result, backend)._value.get()


@pytest.fixture()
def redis_cache():
    return RetrievalCache(enabled=True, client=fakeredis.FakeRedis())


def test_repeat_search_is_a_cache_hit_with_identical_results(index_dir, redis_cache):
    r = FaissRetriever(index_dir, cache=redis_cache)
    ctx = RunContext.new()
    hits0 = _count("results", "hit", "redis")
    first = r.search("source of protein claim condition", ctx, k=5)
    second = r.search("Source of protein   claim condition", ctx, k=5)  # case and spacing do not matter
    assert [p.passage_id for p in first] == [p.passage_id for p in second]
    assert [p.score for p in first] == [p.score for p in second]
    assert _count("results", "hit", "redis") == hits0 + 1


def test_cache_key_includes_index_version(index_dir, redis_cache):
    r = FaissRetriever(index_dir, cache=redis_cache)
    ctx = RunContext.new()
    r.search("allergen declaration", ctx)
    misses = _count("results", "miss", "redis")
    r.version = "a-rebuilt-index"
    r.search("allergen declaration", ctx)
    assert _count("results", "miss", "redis") == misses + 1


def test_query_embeddings_are_cached(index_dir, redis_cache):
    r = FaissRetriever(index_dir, cache=redis_cache, mode="dense")
    ctx = RunContext.new()
    r.search("trans fat free", ctx, k=3)
    hits = _count("embeddings", "hit", "redis")
    r.search("trans fat free", ctx, k=4)  # different k: result-cache miss, embedding-cache hit
    assert _count("embeddings", "hit", "redis") == hits + 1


def test_disabled_cache_never_hits(index_dir):
    r = FaissRetriever(index_dir, cache=RetrievalCache(enabled=False))
    ctx = RunContext.new()
    assert r.search("protein", ctx) == r.search("protein", ctx)
    assert r.cache.get_results("anything") is None


class _DeadRedis:
    def get(self, key):
        raise ConnectionError("redis down")

    def set(self, key, value, ex=None):
        raise ConnectionError("redis down")


def test_redis_outage_degrades_to_memory_without_failing(index_dir, caplog):
    cache = RetrievalCache(enabled=True, client=_DeadRedis())
    r = FaissRetriever(index_dir, cache=cache)
    ctx = RunContext.new()
    assert r.search("protein", ctx)
    assert cache.backend == "memory"
    assert r.search("protein", ctx)  # now served from the in-process LRU
    assert "falling back to in-process memory" in caplog.text


def test_from_env(monkeypatch):
    monkeypatch.setenv("CACHE_ENABLED", "0")
    assert RetrievalCache.from_env().enabled is False
    monkeypatch.setenv("CACHE_ENABLED", "1")
    monkeypatch.setenv("CACHE_TTL_S", "60")
    monkeypatch.delenv("REDIS_URL", raising=False)
    cache = RetrievalCache.from_env()
    assert cache.enabled and cache.ttl_s == 60 and cache.backend == "memory"
