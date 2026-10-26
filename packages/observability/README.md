# fssai_observability (`packages/observability`)

JSON logs, OTel tracing and metric helpers that every service imports (D5, F8). Owner: Nishkal · task N3.1.

```python
from fssai_observability import setup_logging, setup_tracing, span, inject_trace_context, attach_trace_context

setup_logging("worker")   # JSON lines on stderr; run_id/correlation_id from `extra=`; RunContext events flattened
setup_tracing("worker")   # OTel -> OTLP/HTTP at OTEL_EXPORTER_OTLP_ENDPOINT (http://jaeger:4318); no-op if unset

with span("retrieval.search", k=5): ...                 # a child span; nothing at all without OTel
payload["trace"] = inject_trace_context()               # API, when enqueuing a run
with attach_trace_context(payload.get("trace")): ...    # worker: the run joins the API's trace
```

Both setup functions are idempotent and never raise. `setup_logging` replaces a plain `basicConfig` console
handler, so lines are not doubled. `publish_index_manifest` exposes index freshness as `fssai_index_*`
gauges (the retriever calls it when it loads an index).

The stack that receives all this (Prometheus, Grafana, Jaeger, cAdvisor, exporters) is
`infra/compose/observability.yml`, configured from `infra/observability/`.

```bash
<venv-python> -m pip install -e "packages/observability[test]"
<venv-python> -m pytest packages/observability -q
```
