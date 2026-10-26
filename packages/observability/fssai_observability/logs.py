"""JSON-lines logging (D5): one JSON object per record, queryable rather than just readable."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

# LogRecord attributes that are plumbing, not fields worth shipping
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}
_MARK = "_fssai_json_handler"


def _trace_ids() -> dict:
    try:
        from opentelemetry import trace
    except ImportError:
        return {}
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return {}
    return {"trace_id": format(ctx.trace_id, "032x"), "span_id": format(ctx.span_id, "016x")}


class JsonFormatter(logging.Formatter):
    """Fields: ts, level, service, logger, message, plus everything passed with `extra=` (run_id,
    correlation_id, ...), the active trace/span ids, and the exception if any.

    RunContext.event() logs a JSON object as its message; that object is merged into the record
    instead of being nested as a string, so `event`, `run_id` and friends are top-level fields."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        out: dict = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                     "level": record.levelname, "service": self.service, "logger": record.name}
        merged = None
        if message.startswith("{") and message.endswith("}"):
            try:
                merged = json.loads(message)
            except ValueError:
                merged = None
        if isinstance(merged, dict):
            out["message"] = merged.get("event", "")
            out.update({k: v for k, v in merged.items() if k not in ("ts", "level", "service", "logger")})
        else:
            out["message"] = message
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                out[key] = value
        out.update({k: v for k, v in _trace_ids().items() if k not in out})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


def setup_logging(service: str, level: str | None = None) -> None:
    """Route the root logger to stderr as JSON lines. Idempotent: calling it twice still gives one line
    per record. Replaces plain console handlers (e.g. from logging.basicConfig) so lines are not doubled;
    leaves other handlers (files, test capture) alone."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        plain_console = type(handler) is logging.StreamHandler and getattr(handler, "stream", None) in (
            sys.stderr, sys.stdout, sys.__stderr__, sys.__stdout__)
        if getattr(handler, _MARK, False) or plain_console:
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _MARK, True)
    handler.setFormatter(JsonFormatter(service))
    root.addHandler(handler)
    root.setLevel((level or os.environ.get("LOG_LEVEL", "INFO") or "INFO").upper())
