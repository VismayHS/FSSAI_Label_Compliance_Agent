-- Feedback on runs (owner Vihaan; L6). Written by POST /v1/runs/{run_id}/feedback
-- (apps/api/app/routers/feedback.py), aggregated by GET /v1/feedback/summary and charted in
-- infra/observability/grafana/dashboards/quality.json. Applied once when the Postgres volume is first created;
-- IF NOT EXISTS makes it safe to re-apply:
--   docker compose exec -T postgres psql -U fssai -d fssai < infra/postgres/init/21-vihaan-feedback.sql
--
-- route is copied from the run at feedback time, so satisfaction can be grouped by the kind of answer.
-- run_id references runs, so feedback cannot name a run that never existed.

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   text PRIMARY KEY,
    run_id        text NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    satisfactory  boolean NOT NULL,
    reason        text NOT NULL,
    route         text,
    client_id     text,
    submitted_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS feedback_submitted_at_idx ON feedback (submitted_at DESC);
CREATE INDEX IF NOT EXISTS feedback_run_idx ON feedback (run_id);
