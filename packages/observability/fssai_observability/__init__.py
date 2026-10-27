"""Logging, tracing and metric helpers every service calls at start-up (docs/contexts/Nishkal.md N3.1, D5).

    from fssai_observability import setup_logging, setup_tracing
    setup_logging("api")    # JSON lines on stderr, with run_id / correlation_id when a record carries them
    setup_tracing("api")    # OTel -> OTLP/HTTP at OTEL_EXPORTER_OTLP_ENDPOINT; a no-op when that is unset

Both are idempotent and never raise in a process with no observability stack running.
"""
from __future__ import annotations

from .logs import JsonFormatter, setup_logging
from .metrics import publish_index_manifest, start_metrics_server
from .tracing import attach_trace_context, inject_trace_context, setup_tracing, span, tracing_enabled

__all__ = [
    "JsonFormatter", "attach_trace_context", "inject_trace_context", "publish_index_manifest", "setup_logging",
    "setup_tracing", "span", "start_metrics_server", "tracing_enabled",
]
