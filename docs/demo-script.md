# Demo script: the 10 items, in order

Owner: Vismay (S4.3). For the review on **Fri 6 Nov 2026** and the two rehearsals before it. Every command runs from the
repo root on the host, with the stack up (`docker compose up -d --build`). `<py>` is the venv's Python
(`.venv/Scripts/python` on Windows, `.venv/bin/python` on macOS).

## Before you start

- **Groq budget.** The free tier allows about **16 real runs a day per key** (200,000 tokens per model per day;
  `docs/contexts/LLM_Context.md` §4). One full pass of this script uses about 8. So:
  - don't run the eval set or the prompt comparison on the day of a rehearsal or of the review;
  - leave at least a minute between real runs (8,000 tokens per minute);
  - on review day, keep a second teammate's key ready in a spare `.env`.
- **Clean clone, the evening before:** `python tools/scripts/clean_clone_test.py --remote`. Exit 0 means a stranger's
  clone of `main` boots and serves a request. A failed clean clone means zero marks, so this goes first.
- Open these tabs: web client http://localhost:8080 · API docs http://localhost:8000/docs · Jaeger
  http://localhost:16686 · Grafana http://localhost:3000 (dashboards: FSSAI · Service overview, FSSAI · Agents, Quality and trust, Cost).

## The items

| # | Lead | Command | What to show | Real runs |
|---|---|---|---|---|
| 1 | Vismay | `docker compose up -d --build`, then `<py> tools/scripts/smoke.py` | Every service healthy (`docker compose ps`); smoke: ready, one run completed, one reject that started no run | 1 |
| 2 | Namith | `<py> -m fssai_agents.demo --api http://localhost:8000 --only 2` | The route and its reason; every citation resolves to a passage retrieved in this run, with the regulation and clause; a claim label cites both regulations | 1 |
| 3 | Vismay | The run from #2 in the web client, then its **Trace** view; `GET /v1/runs/{id}/trace`; the `jaeger_url` it returns | Each tool call with its query and full passages, prompt versions, per-step latency, tokens and cost, queue wait; the same run in Jaeger | 0 |
| 4 | Vihaan | `<py> packages/eval/tools/demo_trust.py --api http://localhost:8000` (#4 runs first) | 422 with every field error and a quarantine id; `GET /v1/quarantine`; no run row and no queue job | 0 |
| 5 | Vihaan | Same script (#5) | An out-of-corpus product, a claim with no condition in the corpus, and the §4.1 case all go to `regulatory-review` with a reason, not an invented clause | 3 |
| 6 | Vihaan | Same script (#6); if the live run happens to verify first time, `--in-process` shows it deterministically | The verifier rejects a citation that isn't verbatim, retries with a hint, then verifies or escalates; all of it in the trace | 1 |
| 7 | Namith | `<py> -m fssai_agents.demo --api http://localhost:8000 --only 7` | The injection in `front_of_pack_text` is flagged; the guardrail report names the field; no LLM or tool step ran | 0 |
| 8 | Vismay | `docker compose exec worker python -m fssai_llm_gateway.demo` (or `make demo-breaker`) | Stub down: retries, then the breaker opens and calls fail fast with no HTTP; stub up: half-open, then closed. Grafana breaker gauge | 0 (stub) |
| 9 | Nishkal | The committed matrix in `infra/loadtest/results/` against `infra/loadtest/SLO.md`; live, one short step: `<py> infra/loadtest/run_matrix.py --users 5 --duration 60s` with the stub `.env` | p95 against the declared SLO, the concurrency where it breaks, what `--scale worker=3` changes, and the bottleneck | 0 (stub) |
| 10 | Nishkal (+ Namith, Vihaan) | Web client: the built-in example (breakfast cereal, "Source of protein", 8 g per 100 g) | The researcher finds the Claims condition (FSS-AC-2018 Schedule I) and the labelling requirements (FSS-LD-2020); the condition is a % of the RDA, which neither regulation states, so the finding is `cannot_determine` and the route is `regulatory-review` with that reason (until the team settles the RDA question in `docs/eval1/section-4.1-passages.md`) | 1 |

Item 8 drives the gateway straight at the `stub-llm` service, so it needs no `.env` change. Item 9 needs the stub
`.env` from `infra/loadtest/results/README.md`; switch back to the real provider and run
`docker compose up -d --force-recreate worker api` before any real-LLM item.

## If something fails on the day

- A run ends `complete=false` with a `429`: that's the provider's quota. Say so; it is the degradation path (#8)
  doing its job. Switch to the spare key and rerun.
- The stack doesn't come up: `docker compose ps`, then `docker compose logs <service>`; `docs/runbook.md` has the
  two failure modes we have seen most.
- Anyone can be asked about any part (viva). The walkthrough session before the review covers each person's part.
