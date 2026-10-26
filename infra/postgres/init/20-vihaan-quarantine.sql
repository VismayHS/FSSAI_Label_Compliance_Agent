-- Quarantine (owner Vihaan; D1, F2, demo #4): every request the gate rejects, stored with its field errors
-- instead of being discarded. Written by fssai_gate.quarantine.PostgresQuarantine, read by GET /v1/quarantine.
-- Postgres applies this once, when its volume is first created; every statement is IF NOT EXISTS, so it is
-- safe to re-apply by hand:
--   docker compose exec -T postgres psql -U fssai -d fssai < infra/postgres/init/20-vihaan-quarantine.sql
--
-- There is deliberately no foreign key to runs: a rejected request never creates a run (demo #4 shows that
-- no runs row exists for a quarantine_id's request). Rate-limited requests are not quarantined.

CREATE TABLE IF NOT EXISTS quarantine (
    quarantine_id   text PRIMARY KEY,
    received_at     timestamptz NOT NULL,
    client_id       text NOT NULL,
    correlation_id  text,
    schema_version  text,
    error_count     integer NOT NULL,
    error_codes     text[] NOT NULL,           -- distinct FieldError.code values, for filtering and dashboards
    errors          jsonb NOT NULL,            -- [FieldError{loc, message, code}, ...]
    payload         jsonb                      -- the raw request exactly as received
);
CREATE INDEX IF NOT EXISTS quarantine_received_at_idx ON quarantine (received_at DESC);
CREATE INDEX IF NOT EXISTS quarantine_client_idx ON quarantine (client_id, received_at DESC);
CREATE INDEX IF NOT EXISTS quarantine_codes_idx ON quarantine USING gin (error_codes);
