"""What every service relies on from fssai_observability."""
import json
import logging

from fssai_observability import setup_logging, setup_tracing


def test_logs_are_json_lines_with_run_ids(capfd):
    setup_logging("test")
    setup_logging("test")  # idempotent: still one line per record
    logging.getLogger("fssai").warning("hello", extra={"run_id": "r1", "correlation_id": "c1"})
    out, err = capfd.readouterr()
    lines = [line for line in (out + err).splitlines() if "hello" in line]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["service"] == "test" and record["run_id"] == "r1" and record["correlation_id"] == "c1"


def test_tracing_is_a_no_op_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    setup_tracing("test")
    setup_tracing("test")
