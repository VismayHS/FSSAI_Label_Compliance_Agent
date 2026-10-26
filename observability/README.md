# observability

Monitoring configuration, mounted into the `prometheus` and `grafana` services (`deploy/compose/observability.yml`).
Prometheus is at <http://localhost:9090>, Grafana at <http://localhost:3000> and Jaeger at <http://localhost:16686>.

| Path | What | Owner |
|---|---|---|
| `prometheus/prometheus.yml` | Scrape targets: api, worker (every replica), stub-llm, redis, postgres, cAdvisor, Jaeger, Grafana | Nishkal |
| `prometheus/rules/slo.yml` | Recording rules for the SLO: run p50 and p95, HTTP p95, slow-run ratios | Nishkal |
| `grafana/provisioning/` | Datasources (Prometheus, Jaeger, Postgres) and the dashboard provider | Nishkal |
| `grafana/dashboards/service-overview.json` | Latency p50/p95, throughput, error rate, availability, CPU and memory per container, index age and size (D5) | Nishkal |
| `grafana/dashboards/agents.json` | Per-agent success rate, steps, tool calls, latency, retries (A6) | Namith |
| `grafana/dashboards/cost.json` | Cost per 100 runs, per run and per LLM step, tokens and spend by agent, circuit breaker (L5) | Vismay |
| `grafana/dashboards/quality.json` | Live quality scores, user feedback and the ingestion gate (L3, L6, D1); arrives with Vihaan's PR | Vihaan |
