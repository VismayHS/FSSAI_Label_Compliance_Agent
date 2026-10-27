-- Live quality scores (owner Vihaan; L6). `python -m fssai_eval live --sample N` scores a sample of recently
-- completed runs with the same metrics as the offline eval (packages/eval/README.md) and writes one row per run here.
-- Charted in infra/observability/grafana/dashboards/quality.json. IF NOT EXISTS: safe to re-apply:
--   docker compose exec -T postgres psql -U fssai -d fssai < infra/postgres/init/22-vihaan-quality-scores.sql
--
-- (run_id, scorer_version) is unique, so re-running the scorer never double-counts a run.

CREATE TABLE IF NOT EXISTS quality_scores (
    run_id              text NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    scorer_version      text NOT NULL,
    scored_at           timestamptz NOT NULL,
    run_updated_at      timestamptz,
    route               text,
    complete            boolean,
    groundedness        double precision,     -- share of finding statements supported by cited text
    context_relevance   double precision,     -- relevance of retrieved passages to the request
    faithfulness        double precision,     -- share of decisive findings whose status follows from text + values
    hallucinated        boolean,              -- >= 1 unsupported or contradicted statement in this response
    citation_resolution double precision,     -- share of citations that resolve verbatim
    judge               text,                 -- which judge produced the scores (lexical | llm | trulens)
    detail              jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (run_id, scorer_version)
);
CREATE INDEX IF NOT EXISTS quality_scores_scored_at_idx ON quality_scores (scored_at DESC);
