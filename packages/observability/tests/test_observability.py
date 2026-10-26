"""Behaviour beyond the contract: RunContext events, basicConfig take-over, spans, trace propagation, metrics."""
from __future__ import annotations

import json
import logging

from prometheus_client import REGISTRY

from fssai_contracts.context import RunContext
from fssai_observability import (
    attach_trace_context, inject_trace_context, publish_index_manifest, setup_logging, setup_tracing, span,
)
from fssai_observability import tracing as tracing_mod


def _lines(capfd, needle: str) -> list[dict]:
    out, err = capfd.readouterr()
    return [json.loads(line) for line in (out + err).splitlines() if needle in line]


def test_run_context_events_become_top_level_fields(capfd):
    setup_logging("worker")
    ctx = RunContext.new(run_id="run42", correlation_id="corr42")
    ctx.record(agent="researcher", kind="tool", name="corpus_search", latency_ms=12.5)
    (line,) = _lines(capfd, "corpus_search")
    assert line["message"] == "step" and line["event"] == "step"
    assert line["run_id"] == "run42" and line["correlation_id"] == "corr42"
    assert line["agent"] == "researcher" and line["latency_ms"] == 12.5 and line["service"] == "worker"


def test_replaces_a_plain_basic_config_handler(capfd):
    root = logging.getLogger()
    plain = logging.StreamHandler()  # what logging.basicConfig installs
    root.addHandler(plain)
    setup_logging("api")
    assert plain not in root.handlers
    logging.getLogger("x").warning("only-once")
    assert len(_lines(capfd, "only-once")) == 1


def test_exceptions_are_kept(capfd):
    setup_logging("api")
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("x").exception("failed-op")
    (line,) = _lines(capfd, "failed-op")
    assert "ValueError: boom" in line["exc"]


def test_span_works_with_and_without_a_provider():
    with span("retrieval.search", k=5, regulation=None, tags=["a"]) as s:
        assert s is not None  # OpenTelemetry is installed; without a provider the span is a no-op one


def test_tracing_with_an_endpoint_installs_a_provider(monkeypatch):
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http import trace_exporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exported = InMemorySpanExporter()  # stands in for OTLP/HTTP, so the test never touches the network
    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", lambda: exported)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
    monkeypatch.setattr(tracing_mod, "_configured", None)
    assert setup_tracing("worker") is True
    assert setup_tracing("worker") is True  # idempotent
    with span("unit-test", run_id="r1") as s:
        assert s.get_span_context().is_valid
        carrier = inject_trace_context()
    assert "traceparent" in carrier
    with attach_trace_context(carrier):
        assert format(trace.get_current_span().get_span_context().trace_id, "032x") in carrier["traceparent"]
    trace.get_tracer_provider().force_flush()
    (finished,) = [x for x in exported.get_finished_spans() if x.name == "unit-test"]
    assert finished.attributes["run_id"] == "r1"
    assert finished.resource.attributes["service.name"] == "worker"


def test_attach_tolerates_an_empty_carrier():
    with attach_trace_context(None):
        pass
    with attach_trace_context({}):
        pass


def test_index_freshness_metrics():
    manifest = {"built_at": "2026-10-25T08:00:00+00:00", "index_version": "abc", "embedding_model": "m",
                "throughput": {"chunks_per_second": 47.0},
                "documents": [{"regulation": "FSS-AC-2018", "doc_version": "Version-II (2021-11-16)",
                               "sha256": "347a16b05d1e9796" + "0" * 48}]}
    publish_index_manifest(manifest, {("FSS-AC-2018", "in_force"): 180, ("FSS-AC-2018", "superseded"): 30})
    get = REGISTRY.get_sample_value
    assert get("fssai_index_built_timestamp_seconds") == 1792915200.0
    assert get("fssai_index_chunks_total", {"regulation": "FSS-AC-2018", "status": "in_force"}) == 180
    assert get("fssai_ingest_chunks_per_second") == 47.0
    assert get("fssai_index_doc_version_info", {"regulation": "FSS-AC-2018", "doc_version": "Version-II (2021-11-16)",
                                                "sha256": "347a16b05d1e9796"}) == 1
    assert get("fssai_index_info", {"index_version": "abc", "embedding_model": "m"}) == 1
