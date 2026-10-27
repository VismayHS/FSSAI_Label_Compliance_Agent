# fssai_run_store

`PostgresRunStore`, the shared `RunStore` (D5, A7). The API saves each run as `queued`, a worker updates it, and
any replica can read it, so the workers stay stateless. Owner: Vismay. Compose switches it on for `api` and `worker`.

- Table `runs`: one row per run, with the full `RunStatus` in a `jsonb` column.
- Table `run_steps`: one row per step, so cost and latency can be queried in SQL (`tools/scripts/cost_report.py`, the cost dashboard).
- Schema: [`infra/postgres/init/10-vismay-runs.sql`](../../infra/postgres/init/10-vismay-runs.sql).
- An older save never overwrites a newer one (an `updated_at` check), so out-of-order writes are safe.

```bash
FSSAI_TEST_DATABASE_URL=postgresql://... <venv-python> -m pytest packages/run_store -q   # skipped without a database
```
