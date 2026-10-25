"""OpenTelemetry tracing (D5): OTLP over HTTP to Jaeger (or Tempo). A no-op when not configured.

    setup_tracing("worker")                     # once at start-up
    with span("retrieval.search", k=5): ...     # a child span, or nothing at all without OTel

Across the queue (API -> RQ job -> worker) the trace continues through the job payload:
    payload["trace"] = inject_trace_context()            # API, when enqueuing
    with attach_trace_context(payload.get("trace")): ... # worker, around the run
"""
from __future__ import annotations

import logging
import os
import socket
from contextlib import contextmanager
from typing import Iterator

log = logging.getLogger("fssai.observability")
_configured: str | None = None


def tracing_enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").split("#", 1)[0].strip())


def setup_tracing(service: str) -> bool:
    """Install the OTel SDK with an OTLP/HTTP exporter at OTEL_EXPORTER_OTLP_ENDPOINT (e.g.
    http://jaeger:4318). Returns True if tracing is on. Never raises: tracing must not stop a service."""
    global _configured
    if not tracing_enabled():
        return False
    if _configured:
        return True
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        log.warning("tracing requested but OpenTelemetry is not installed: %s", exc)
        return False
    try:
        resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME") or service,
                                    "service.instance.id": socket.gethostname()})
        provider = TracerProvider(resource=resource)
        # the exporter reads OTEL_EXPORTER_OTLP_ENDPOINT itself and appends /v1/traces
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
    except Exception as exc:  # noqa: BLE001 - a bad endpoint must not take the service down
        log.warning("tracing disabled: %s", exc)
        return False
    _configured = service
    return True


@contextmanager
def span(name: str, **attributes) -> Iterator[object | None]:
    """A span named `name` with `attributes`; yields None and does nothing if OTel is not installed."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return
    with trace.get_tracer("fssai").start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value if isinstance(value, (str, bool, int, float)) else str(value))
        yield current


def inject_trace_context() -> dict:
    """The current trace context as a plain dict (W3C traceparent), to carry inside a job payload."""
    try:
        from opentelemetry.propagate import inject
    except ImportError:
        return {}
    carrier: dict = {}
    inject(carrier)
    return carrier


@contextmanager
def attach_trace_context(carrier: dict | None) -> Iterator[None]:
    """Continue the trace that `carrier` came from (see inject_trace_context)."""
    if not carrier:
        yield
        return
    try:
        from opentelemetry import context
        from opentelemetry.propagate import extract
    except ImportError:
        yield
        return
    token = context.attach(extract(carrier))
    try:
        yield
    finally:
        context.detach(token)
