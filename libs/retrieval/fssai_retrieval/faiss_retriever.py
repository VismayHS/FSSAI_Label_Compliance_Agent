"""FaissRetriever: the real Retriever (contexts/Nishkal.md N2.2, N3.3; decisions 002 and 003).

search(query, ctx, k, regulation)
    Hybrid by default (RETRIEVAL_MODE=hybrid): dense FAISS similarity (LangChain store, local
    sentence-transformers embeddings) and BM25 over the same chunks, plus claim-trigger hints, fused by
    reciprocal rank. Superseded text is left out (RETRIEVAL_INCLUDE_SUPERSEDED=1 to keep it). With
    `regulation` set, filtering happens before ranking, so the filter never starves k.
get_clause(regulation, clause_id, ctx)
    Exact lookup after normalising spacing, brackets and wording ("5 (3)" == "5(3)", "Schedule-I item 11"
    == "Schedule I, item 11"). A clause stored as several chunks (sub-clauses or parts) comes back as one
    passage with their texts joined in document order. None if the clause does not exist: never a near match.

Records no steps: the agent records the tool step with the passages it got back (LLM_Context §6.4).
Results and query embeddings are cached in Redis (CACHE_ENABLED), keyed by index version (decision 003).
The index is reloaded when index_manifest.json changes, so a rebuild needs no worker restart.

Switch on: IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from prometheus_client import Counter, Histogram

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Passage, Regulation

from .bm25 import BM25
from .cache import RetrievalCache, digest, env_flag
from .hints import ClaimHints
from .index import (
    FAISS_NAME, MANIFEST, TRIGGERS, Chunk, IndexNotBuilt, get_embeddings, index_version, l2_to_similarity,
    normalise_clause_id, read_json, read_passages,
)

log = logging.getLogger("fssai.retrieval")

MODES = ("hybrid", "dense", "bm25")
RRF_K = 60  # reciprocal-rank fusion constant (Cormack et al.); damps the weight of any single rank

RETRIEVAL_SECONDS = Histogram("fssai_retrieval_seconds", "Retriever latency", ["op", "cache"],
                              buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
RETRIEVAL_EMPTY = Counter("fssai_retrieval_empty_total", "Searches or lookups that found nothing", ["op"])
RETRIEVAL_DEGRADED = Counter("fssai_retrieval_degraded_total", "Dense retrieval unavailable; served by BM25", [])


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip() or default


class FaissRetriever:
    def __init__(self, index_dir: Path, *, mode: str | None = None, cache: RetrievalCache | None = None,
                 hints: bool | None = None, include_superseded: bool | None = None, embeddings=None,
                 reranker=None, rerank_top: int = 20) -> None:
        self.index_dir = Path(index_dir)
        self.mode = (mode or _env("RETRIEVAL_MODE", "hybrid")).lower()
        if self.mode not in MODES:
            raise ValueError(f"RETRIEVAL_MODE must be one of {MODES}, not {self.mode!r}")
        self.cache = cache if cache is not None else RetrievalCache(enabled=False)
        self.use_hints = env_flag("RETRIEVAL_CLAIM_HINTS", True) if hints is None else hints
        self.include_superseded = (env_flag("RETRIEVAL_INCLUDE_SUPERSEDED", False)
                                   if include_superseded is None else include_superseded)
        self.reranker = reranker
        self.rerank_top = rerank_top
        self._embeddings = embeddings
        self._lock = threading.RLock()
        self._loaded_mtime: float | None = None
        self._last_check = 0.0
        self.degraded_reason: str | None = None
        self._load()

    @classmethod
    def from_registry(cls) -> FaissRetriever:
        reranker = None
        if _env("RERANKER_MODEL"):
            reranker = CrossEncoderReranker(_env("RERANKER_MODEL"))
        return cls(Path(_env("INDEX_DIR", "/data/index")), cache=RetrievalCache.from_env(), reranker=reranker)

    # ------------------------------------------------------------ loading

    def _load(self) -> None:
        manifest_path = self.index_dir / MANIFEST
        if not manifest_path.exists():
            raise IndexNotBuilt(f"no index in {self.index_dir}: run python -m fssai_ingest build "
                                f"--corpus corpus/raw --out {self.index_dir}")
        manifest = read_json(manifest_path, {})
        chunks = read_passages(self.index_dir)
        self.manifest = manifest
        self.version = index_version(manifest)
        self.chunks = chunks
        self.by_id = {c.passage_id: c for c in chunks}
        self.order = {c.passage_id: i for i, c in enumerate(chunks)}
        self.searchable = [i for i, c in enumerate(chunks) if self.include_superseded or c.in_force]
        self.bm25 = BM25([c.embed_text for c in chunks])
        self.by_clause: dict[tuple[str, str], list[Chunk]] = {}
        self.by_subclause: dict[tuple[str, str], tuple[Chunk, str, int, int]] = {}
        for c in chunks:
            if c.in_force:
                self.by_clause.setdefault((c.regulation, normalise_clause_id(c.clause_id)), []).append(c)
                for sub, (start, end) in (c.extra or {}).get("subclauses", {}).items():
                    self.by_subclause.setdefault((c.regulation, normalise_clause_id(sub)), (c, sub, start, end))
        self.hints = ClaimHints.load(self.index_dir / TRIGGERS) if self.use_hints else None
        self.store = None
        if self.mode != "bm25":
            self._load_dense()
        self._loaded_mtime = manifest_path.stat().st_mtime
        try:
            from fssai_observability.metrics import publish_index_manifest

            counts: dict[tuple[str, str], int] = {}
            for c in chunks:
                counts[(c.regulation, c.status)] = counts.get((c.regulation, c.status), 0) + 1
            publish_index_manifest(manifest, counts)
        except ImportError:  # pragma: no cover - observability is a dependency; metrics are best effort
            pass
        log.info("retriever loaded index %s: %d chunks, mode=%s, model=%s", self.version, len(chunks),
                 self.effective_mode, manifest.get("embedding_model"))

    def _load_dense(self) -> None:
        alias = self.manifest.get("embedding_model")
        env_alias = _env("EMBEDDING_MODEL")
        if env_alias and alias and env_alias != alias:
            log.warning("EMBEDDING_MODEL=%s differs from the model that built the index (%s); using the index's",
                        env_alias, alias)
        try:
            from langchain_community.vectorstores import FAISS

            self._embeddings = self._embeddings or get_embeddings(alias)
            self.store = FAISS.load_local(str(self.index_dir), self._embeddings, index_name=FAISS_NAME,
                                          allow_dangerous_deserialization=True)  # our own index volume, not user input
            self.model_alias = alias
            self.degraded_reason = None
        except Exception as exc:  # noqa: BLE001 - degrade to lexical search rather than fail every run
            self.store = None
            self.degraded_reason = f"dense retrieval unavailable ({type(exc).__name__}: {exc}); serving BM25 only"
            log.error("retriever: %s", self.degraded_reason)

    @property
    def effective_mode(self) -> str:
        return self.mode if self.store is not None or self.mode == "bm25" else "bm25"

    def _maybe_reload(self) -> None:
        now = time.monotonic()
        if now - self._last_check < 5:
            return
        self._last_check = now
        try:
            mtime = (self.index_dir / MANIFEST).stat().st_mtime
        except FileNotFoundError:
            return
        if mtime != self._loaded_mtime:
            with self._lock:
                if mtime != self._loaded_mtime:
                    log.info("retriever: index changed on disk, reloading")
                    self._load()

    # ------------------------------------------------------------ search

    def search(self, query: str, ctx: RunContext, *, k: int = 5,
               regulation: Regulation | None = None) -> list[Passage]:
        t0 = time.perf_counter()
        self._maybe_reload()
        reg = Regulation(regulation).value if regulation is not None else None
        mode = self.effective_mode
        key = digest(self.version, mode, self.use_hints, self.include_superseded, bool(self.reranker), reg, k,
                     " ".join(query.lower().split()))
        cached = self.cache.get_results(key)
        if cached is not None:
            hits = [self.by_id[pid].to_passage(score) for pid, score in cached if pid in self.by_id]
            RETRIEVAL_SECONDS.labels("search", "hit").observe(time.perf_counter() - t0)
            return hits
        ranked = [(c, round(s, 6)) for c, s in self.rank(query, k=k, regulation=reg)]
        self.cache.set_results(key, [[c.passage_id, s] for c, s in ranked])
        if not ranked:
            RETRIEVAL_EMPTY.labels("search").inc()
        RETRIEVAL_SECONDS.labels("search", "miss" if self.cache.enabled else "off").observe(time.perf_counter() - t0)
        return [c.to_passage(s) for c, s in ranked]

    def rank(self, query: str, *, k: int = 5, regulation: str | None = None,
             mode: str | None = None) -> list[tuple[Chunk, float]]:
        """The ranking behind search(), without caching. Exposed for evaluation (fssai_retrieval.evaluate)."""
        mode = mode or self.effective_mode
        allowed = {i for i in self.searchable if regulation is None or self.chunks[i].regulation == regulation}
        if not allowed or k <= 0:
            return []
        depth = max(k * 10, 50)
        lists: list[list[int]] = []
        dense_scores: dict[int, float] = {}
        if mode in ("dense", "hybrid") and self.store is not None:
            dense = self._dense(query, depth, allowed)
            dense_scores = dict(dense)
            lists.append([i for i, _ in dense])
        if mode in ("bm25", "hybrid") or (mode == "dense" and self.store is None):
            lists.append([i for i, _ in self.bm25.top(query, depth, allowed)])
        if self.hints is not None and mode == "hybrid":
            lists.append(self._hint_ranks(query, allowed))
        if mode == "dense" and len(lists) == 1 and dense_scores:
            ranked = [(i, dense_scores[i]) for i in lists[0]]
        else:
            fused: dict[int, float] = {}
            for ranking in lists:
                for r, i in enumerate(ranking, start=1):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r)
            ranked = sorted(fused.items(), key=lambda t: (-t[1], t[0]))
        if self.reranker is not None and ranked:
            head = ranked[: self.rerank_top]
            scores = self.reranker(query, [self.chunks[i].text for i, _ in head])
            ranked = sorted(zip((i for i, _ in head), scores), key=lambda t: -t[1]) + ranked[self.rerank_top:]
        return [(self.chunks[i], float(s)) for i, s in ranked[:k]]

    def _query_vector(self, query: str) -> list[float]:
        key = digest(self.model_alias, query)
        vec = self.cache.get_vector(key)
        if vec is None:
            vec = self._embeddings.embed_query(query)
            self.cache.set_vector(key, vec)
        return vec

    def _dense(self, query: str, depth: int, allowed: set[int]) -> list[tuple[int, float]]:
        try:
            vec = self._query_vector(query)
            n = min(self.store.index.ntotal, max(depth * 3, 100))
            found = self.store.similarity_search_with_score_by_vector(vec, k=n)
        except Exception as exc:  # noqa: BLE001
            RETRIEVAL_DEGRADED.inc()
            log.error("retriever: dense search failed (%s); using BM25 for this query", exc)
            return []
        out = []
        for doc, distance in found:
            i = self.order.get(doc.metadata.get("passage_id"))
            if i is not None and i in allowed:
                out.append((i, l2_to_similarity(distance)))
        return out[:depth]

    def _hint_ranks(self, query: str, allowed: set[int]) -> list[int]:
        out: list[int] = []
        for ref in self.hints.match(query):
            for c in self.by_clause.get((ref.regulation, normalise_clause_id(ref.clause_id)), []):
                i = self.order[c.passage_id]
                if i in allowed and i not in out:
                    out.append(i)
        return out

    # ------------------------------------------------------------ clause lookup

    def get_clause(self, regulation: Regulation, clause_id: str, ctx: RunContext) -> Passage | None:
        t0 = time.perf_counter()
        self._maybe_reload()
        reg = Regulation(regulation).value
        target = normalise_clause_id(clause_id)
        parts = [c for (r, cid), cs in self.by_clause.items() if r == reg and
                 (cid == target or cid.startswith(target + "(") or cid.startswith(target + " ")) for c in cs]
        RETRIEVAL_SECONDS.labels("get_clause", "off").observe(time.perf_counter() - t0)
        if not parts:
            inside = self.by_subclause.get((reg, target))
            if inside is not None:  # a sub-clause merged into its parent's chunk: return its verbatim slice
                chunk, sub, start, end = inside
                return Passage(passage_id=f"{chunk.passage_id}@{sub}", regulation=Regulation(reg), clause_id=sub,
                               heading_path=list(chunk.heading_path), text=chunk.text[start:end],
                               doc_version=chunk.doc_version)
            RETRIEVAL_EMPTY.labels("get_clause").inc()
            return None
        parts.sort(key=lambda c: self.order[c.passage_id])
        if len(parts) == 1:
            return parts[0].to_passage()
        exact = [c for c in parts if normalise_clause_id(c.clause_id) == target]
        canonical = exact[0].clause_id if exact else clause_id.strip()
        first = exact[0] if exact else parts[0]
        return Passage(passage_id=f"{reg}:{canonical}#all", regulation=Regulation(reg), clause_id=canonical,
                       heading_path=list(first.heading_path), text=" ".join(c.text for c in parts),
                       doc_version=first.doc_version)

    # ------------------------------------------------------------ introspection

    def stats(self) -> dict:
        return {"index_version": self.version, "chunks": len(self.chunks), "searchable": len(self.searchable),
                "mode": self.effective_mode, "degraded": self.degraded_reason, "hints": self.hints is not None,
                "cache": {"enabled": self.cache.enabled, "backend": self.cache.backend},
                "embedding_model": self.manifest.get("embedding_model"), "built_at": self.manifest.get("built_at")}


class CrossEncoderReranker:
    """Optional second stage (RERANKER_MODEL): re-scores the fused top results with a cross-encoder."""

    def __init__(self, model: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model, device=_env("EMBEDDING_DEVICE", "cpu"))

    def __call__(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(query, t) for t in texts])]
