"""Retrieval cache (D7): query embeddings and search results, in Redis so every worker replica shares it.

Keys carry the index version (results) or the embedding model (vectors), so rebuilding the index or
changing the model invalidates the cache with no flush. If Redis is unreachable the cache falls back
to a per-process LRU and says so once in the log: a cache must never fail a run.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict

import numpy as np
from prometheus_client import Counter

log = logging.getLogger("fssai.retrieval")

CACHE_EVENTS = Counter("fssai_retrieval_cache_total", "Retrieval cache lookups",
                       ["cache", "result", "backend"])  # cache: results | embeddings; result: hit | miss


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").split("#", 1)[0].strip().lower()
    return default if not raw else raw in ("1", "true", "yes", "on")


def digest(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:32]


class _Memory:
    def __init__(self, size: int = 4096) -> None:
        self.size = size
        self.data: OrderedDict[str, bytes] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self.lock:
            value = self.data.get(key)
            if value is not None:
                self.data.move_to_end(key)
            return value

    def set(self, key: str, value: bytes, ttl_s: int) -> None:  # noqa: ARG002 - LRU, not time-based
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


class RetrievalCache:
    def __init__(self, enabled: bool = True, redis_url: str | None = None, ttl_s: int = 86400,
                 client=None) -> None:
        self.enabled = enabled
        self.ttl_s = ttl_s
        self.memory = _Memory()
        self.redis = client
        self.backend = "redis" if client is not None else "memory"
        if enabled and client is None and redis_url:
            try:
                import redis

                self.redis = redis.Redis.from_url(redis_url, socket_timeout=0.25, socket_connect_timeout=0.25)
                self.backend = "redis"
            except Exception as exc:  # noqa: BLE001
                log.warning("retrieval cache: redis unavailable (%s); using in-process memory", exc)
        self._warned = False

    @classmethod
    def from_env(cls) -> RetrievalCache:
        ttl = os.environ.get("CACHE_TTL_S", "").split("#", 1)[0].strip()
        return cls(enabled=env_flag("CACHE_ENABLED", True),
                   redis_url=os.environ.get("REDIS_URL", "").split("#", 1)[0].strip() or None,
                   ttl_s=int(ttl) if ttl else 86400)

    # ------------------------------------------------------------ raw

    def _get(self, key: str) -> bytes | None:
        if self.redis is not None and self.backend == "redis":
            try:
                return self.redis.get(key)
            except Exception as exc:  # noqa: BLE001 - degrade, never fail the search
                self._degrade(exc)
        return self.memory.get(key)

    def _set(self, key: str, value: bytes) -> None:
        if self.redis is not None and self.backend == "redis":
            try:
                self.redis.set(key, value, ex=self.ttl_s)
                return
            except Exception as exc:  # noqa: BLE001
                self._degrade(exc)
        self.memory.set(key, value, self.ttl_s)

    def _degrade(self, exc: Exception) -> None:
        if not self._warned:
            log.warning("retrieval cache: redis error (%s); falling back to in-process memory", type(exc).__name__)
            self._warned = True
        self.backend = "memory"

    def _count(self, cache: str, hit: bool) -> None:
        CACHE_EVENTS.labels(cache, "hit" if hit else "miss", self.backend).inc()

    # ------------------------------------------------------------ typed

    def get_results(self, key: str) -> list | None:
        if not self.enabled:
            return None
        raw = self._get(f"fssai:retr:{key}")
        self._count("results", raw is not None)
        return json.loads(raw) if raw is not None else None

    def set_results(self, key: str, value: list) -> None:
        if self.enabled:
            self._set(f"fssai:retr:{key}", json.dumps(value).encode())

    def get_vector(self, key: str) -> list[float] | None:
        if not self.enabled:
            return None
        raw = self._get(f"fssai:emb:{key}")
        self._count("embeddings", raw is not None)
        return np.frombuffer(raw, dtype=np.float32).tolist() if raw is not None else None

    def set_vector(self, key: str, vector: list[float]) -> None:
        if self.enabled:
            self._set(f"fssai:emb:{key}", np.asarray(vector, dtype=np.float32).tobytes())
