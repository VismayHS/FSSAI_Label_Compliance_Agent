"""Logging, tracing and metric helpers every service calls at start-up (contexts/Nishkal.md N3.1). Day-0 skeleton.

- setup_logging(service): JSON lines (one object per record) with service, level and message, plus
  run_id and correlation_id when the record carries them (logging `extra=`).
- setup_tracing(service): OTel SDK -> OTLP exporter at OTEL_EXPORTER_OTLP_ENDPOINT; a no-op when that is unset.
Both are idempotent and never raise in a process with no observability stack running. The API and
worker call them once these work (Vismay, S2.2).
"""
from __future__ import annotations


def setup_logging(service: str) -> None:
    raise NotImplementedError("N3.1: JSON-lines logging with run_id / correlation_id")


def setup_tracing(service: str) -> None:
    raise NotImplementedError("N3.1: OTel tracing; a no-op without OTEL_EXPORTER_OTLP_ENDPOINT")
