"""Prometheus helpers shared by every service (D2, D5).

Index freshness (D2) is published by whichever process loads the index (the worker, through the
retriever), because the indexer is a one-shot job with nothing left to scrape once it exits:

    fssai_index_built_timestamp_seconds          when the loaded index was built (unix time)
    fssai_index_chunks_total{regulation,status}  chunks in the loaded index
    fssai_index_doc_version_info{regulation,doc_version,sha256}   always 1; the versions indexed
    fssai_ingest_chunks_per_second               embedding throughput of the build that made it
    fssai_index_info{index_version,embedding_model}               always 1; which index is loaded
"""
from __future__ import annotations

from datetime import datetime

from prometheus_client import Gauge, start_http_server

INDEX_BUILT = Gauge("fssai_index_built_timestamp_seconds", "When the loaded regulation index was built")
INDEX_CHUNKS = Gauge("fssai_index_chunks_total", "Chunks in the loaded index", ["regulation", "status"])
INDEX_DOC_VERSION = Gauge("fssai_index_doc_version_info", "Document versions in the loaded index",
                          ["regulation", "doc_version", "sha256"])
INGEST_THROUGHPUT = Gauge("fssai_ingest_chunks_per_second", "Embedding throughput of the build that made the index")
INDEX_INFO = Gauge("fssai_index_info", "The loaded index", ["index_version", "embedding_model"])


def publish_index_manifest(manifest: dict, chunk_counts: dict[tuple[str, str], int] | None = None) -> None:
    """Expose an index_manifest.json (written by fssai_ingest) as gauges. Safe to call on every reload."""
    built = manifest.get("built_at")
    if built:
        INDEX_BUILT.set(datetime.fromisoformat(built).timestamp())
    for metric in (INDEX_CHUNKS, INDEX_DOC_VERSION, INDEX_INFO):
        metric.clear()
    for (regulation, status), n in (chunk_counts or {}).items():
        INDEX_CHUNKS.labels(regulation, status).set(n)
    for doc in manifest.get("documents", []):
        INDEX_DOC_VERSION.labels(doc.get("regulation", ""), doc.get("doc_version", ""),
                                 doc.get("sha256", "")[:16]).set(1)
    INGEST_THROUGHPUT.set((manifest.get("throughput") or {}).get("chunks_per_second") or 0)
    INDEX_INFO.labels(manifest.get("index_version", ""), manifest.get("embedding_model", "")).set(1)


def start_metrics_server(port: int) -> None:
    """Serve /metrics on `port` for processes without an HTTP framework (the worker already does this)."""
    start_http_server(port)
