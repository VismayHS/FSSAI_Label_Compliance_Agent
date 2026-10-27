# Eval results

One file per run: `python -m fssai_eval run --tag <tag>` writes `<tag>.json`. Each holds the git sha, the judge, the
`IMPL_*` and prompt settings that were measured (never secrets), the aggregates, the metric definitions and one row
per scenario. Compare two with `python -m fssai_eval compare <before> <after>`.

Commit the results quoted in the report (decision 205: `researcher-1.0.0`, `researcher-1.1.0`) and the CI baseline.
Leave scratch runs out.
