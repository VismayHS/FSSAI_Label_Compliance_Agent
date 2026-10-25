-- Runs and their step traces (owner Vismay; D5, L5). Postgres applies every file in this folder once, when
-- its volume is first created; every statement is IF NOT EXISTS, so re-applying by hand is safe:
--   docker compose exec -T postgres psql -U fssai -d fssai < deploy/postgres/init/10-vismay-runs.sql
-- This file is the only copy of the schema; libs/run_store's tests apply it too.
--
-- runs.doc holds the full RunStatus (request, result, error) exactly as the API returns it; the other
-- columns are copies for filtering and dashboards. run_steps has one row per StepRecord of a finished
-- run, so a run can be reconstructed, and cost per step summed, in plain SQL (S3.2):
--   SELECT name, sum(cost_usd) FROM run_steps GROUP BY name ORDER BY 2 DESC;

CREATE TABLE IF NOT EXISTS runs (
    run_id          text PRIMARY KEY,
    state           text NOT NULL,
    submitted_at    timestamptz NOT NULL,
    updated_at      timestamptz NOT NULL,
    client_id       text,
    correlation_id  text,
    product_name    text,
    route           text,
    complete        boolean,
    cost_usd        double precision,
    doc             jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_updated_at_idx ON runs (updated_at DESC);
CREATE INDEX IF NOT EXISTS runs_route_idx ON runs (route);

CREATE TABLE IF NOT EXISTS run_steps (
    run_id             text NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    step_index         integer NOT NULL,
    agent              text NOT NULL,
    kind               text NOT NULL,
    name               text NOT NULL,
    started_at         timestamptz NOT NULL,
    latency_ms         double precision NOT NULL DEFAULT 0,
    prompt_name        text,
    prompt_version     text,
    prompt_tokens      integer NOT NULL DEFAULT 0,
    completion_tokens  integer NOT NULL DEFAULT 0,
    cost_usd           double precision NOT NULL DEFAULT 0,
    error              text,
    input              jsonb NOT NULL DEFAULT '{}'::jsonb,
    output             jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (run_id, step_index)
);
CREATE INDEX IF NOT EXISTS run_steps_name_idx ON run_steps (name);
