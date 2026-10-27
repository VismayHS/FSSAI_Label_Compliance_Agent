# fssai_gate (`packages/gate`)

The ingestion boundary (F2, D1) and per-client rate limiting (D7). Nothing reaches an agent without passing it.
The published contract it enforces: [`docs/data-contract.md`](../../docs/data-contract.md). Design and rejected
options: [decision 203](../../docs/decisions/203-vihaan-gate-boundary.md).

**Owner:** Vihaan · tasks V1.1, V1.2 in [`docs/contexts/Vihaan.md`](../../docs/contexts/Vihaan.md).

| File | What |
|---|---|
| `fssai_gate/gate.py` | `RequestGate`, the `RequestGate` seam: rate limit → validate → quarantine; backends from env |
| `fssai_gate/rules.py` | The contract's rules as pure functions: schema/type, unknown fields, version, ranges, lengths, formats, category, cross-field XF-01..XF-10 |
| `fssai_gate/ratelimit.py` | Token bucket: Redis (one Lua script, shared by replicas, fails open) or in memory |
| `fssai_gate/quarantine.py` | Quarantine stores: in memory (bounded) or Postgres (`infra/postgres/init/20-vihaan-quarantine.sql`) |
| `tests/` | conformance, one test per rule, gate behaviour, Hypothesis property tests, Postgres (skipped without `FSSAI_TEST_DATABASE_URL`) |

```bash
<venv-python> -m pip install -e "packages/gate[test]"
<venv-python> -m pytest packages/gate -q
<venv-python> packages/eval/tools/export_schema.py          # regenerate docs/data-contract.schema.json after changing a rule
```

**Switched on with** `IMPL_GATE=fssai_gate.gate:RequestGate`. Env: `RATE_LIMIT_PER_MIN`, `RATE_LIMIT_BURST`,
`RATE_LIMIT_BACKEND` (auto/redis/memory), `QUARANTINE_STORE` (auto/postgres/memory), `REDIS_URL`, `DATABASE_URL`,
`CORPUS_CATEGORIES`. Metrics on the API's `/metrics`: `fssai_gate_decisions_total{outcome}`,
`fssai_gate_field_errors_total{code}`.
