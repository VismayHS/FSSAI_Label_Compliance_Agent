# Runbook (D8)

Owner: Namith. The two failure modes most likely to hit this system, each with the symptom, how to confirm it and how to
recover. Every command is run from the repo root. Grafana is at http://localhost:3000, Prometheus at http://localhost:9090,
the API at http://localhost:8000. Real incidents are written up in `docs/incidents/`.

The system never approves a label, so both failures end the same safe way: the run is routed to `regulatory-review`
with a reason. Nothing is ever "cleared" because a dependency was down. What these failures cost is answers, not safety.

---

## 1. The LLM provider is rate-limited or down (circuit breaker open)

**What the user sees.** Runs finish quickly with `complete: false`, route `regulatory-review` and an escalation reason that
starts with `ProviderUnavailable`. The web client shows "run did not complete; no confident answer".

**Symptom on the dashboards**
- Grafana *FSSAI · Agents*: **Task success rate** drops, **Runs by agent and outcome** shows `failure` for `classifier`,
  and **End-to-end run latency** falls (runs end early).
- Grafana *FSSAI · Cost*: LLM calls with a non-success outcome.
- Prometheus alert `RunFailureSLOFastBurn` or `RunFailureSLOSlowBurn` fires when it lasts.

**Confirm it**
```bash
# 1. Breaker state per provider: 0 closed, 1 half-open, 2 open
curl -s 'http://localhost:9090/api/v1/query?query=fssai_llm_breaker_state'
# 2. Why calls fail: outcomes by agent and step
curl -s 'http://localhost:9090/api/v1/query?query=sum by (agent,step,outcome) (increase(fssai_llm_calls_total[10m]))'
# 3. The provider's own words (HTTP 429 = rate limit, 401/403 = bad key, 5xx/timeouts = provider down)
docker compose logs --since 10m worker | grep -i -E "breaker|429|401|403|provider|timeout"
# 4. One failed run, end to end (the last step's error and the escalation reason)
curl -s http://localhost:8000/v1/runs/<run_id>/trace
```
A rate limit is the usual cause on a free tier: `fssai_llm_retries_total` climbs and the log shows 429.

**Recover**
1. **Rate limit (429).** Wait for the breaker cooldown (`BREAKER_COOLDOWN_S`, default 30 s): it goes half-open and closes
   by itself after a successful call. If you are load testing, lower the request rate or point at the stub
   (`LLM_BASE_URL=http://stub-llm:8080/v1`, `LLM_MODEL=stub`).
2. **Bad or expired key (401/403).** Fix `LLM_API_KEY` in `.env`, then `docker compose up -d worker` (the worker reads
   `.env` at start, so it must be recreated, not just restarted).
3. **Provider outage.** Set the fallback provider (`LLM_FALLBACK_BASE_URL`, `LLM_FALLBACK_API_KEY`,
   `LLM_FALLBACK_MODEL`) in `.env` and `docker compose up -d worker`.
4. **Re-run the affected requests.** Runs that ended `complete: false` are not retried automatically. Submit them again
   once `fssai_llm_breaker_state` is `0` for every provider.
5. Write an incident entry (`docs/incidents/YYYY-MM-DD-<name>-<slug>.md`) with the cause and how long it lasted.

**Do not** raise `BREAKER_FAILURE_THRESHOLD` to "make errors go away": the breaker is what stops every run waiting out
a timeout against a dead provider.

---

## 2. The index is missing or stale (retrieval returns nothing)

**What the user sees.** Runs complete, but findings are `cannot_determine`, carry no citations and the route is
`regulatory-review` with escalation signals such as "no provision found". If the index is missing entirely, the worker
cannot start the retriever and runs end `complete: false`.

**Symptom on the dashboards**
- Grafana *FSSAI · Agents*: **Tool calls per run** high (the researcher keeps searching) while the share of runs that
  route to `regulatory-review` rises (*FSSAI · Service overview*, run throughput by route).
- Prometheus: `fssai_retrieval_empty_total` increasing, `fssai_retrieval_degraded_total` increasing (dense search failed,
  BM25 served), or `fssai_index_built_timestamp_seconds` very old (alert `IndexStale`, over 30 days).

**Confirm it**
```bash
# 1. Is there an index, and what does it say it holds?
docker compose run --rm --entrypoint sh indexer -c 'ls -l /data/index && cat /data/index/index_manifest.json | head -40'
# 2. Searches that found nothing, and fallbacks to BM25
curl -s 'http://localhost:9090/api/v1/query?query=sum by (op) (increase(fssai_retrieval_empty_total[10m]))'
curl -s 'http://localhost:9090/api/v1/query?query=increase(fssai_retrieval_degraded_total[10m])'
# 3. Age of the loaded index, in days
curl -s 'http://localhost:9090/api/v1/query?query=(time()-fssai_index_built_timestamp_seconds)/86400'
# 4. Chunks per regulation: both FSS-LD-2020 and FSS-AC-2018 must be present and non-zero
curl -s 'http://localhost:9090/api/v1/query?query=fssai_index_chunks_total'
# 5. A startup failure shows here (IndexNotBuilt means the volume is empty)
docker compose logs --since 10m worker indexer | grep -i -E "IndexNotBuilt|no index|error"
```
If only `FSS-LD-2020` chunks exist, claim conditions in `FSS-AC-2018` cannot be found and every claim escalates: that is
the exact "provision that modifies another" failure this project exists to catch.

**Recover**
1. **Missing or incomplete index.** Rebuild it. The build is idempotent (same chunk ids, only changed text is
   re-embedded), so it is safe to run again:
   ```bash
   docker compose run --rm indexer            # runs: build --reembed changed
   docker compose up -d --force-recreate worker   # the worker loads the index at start
   ```
2. **Stale index after a regulation update.** Replace the PDF in `data/corpus/raw/` (and its version in `sources.yaml`), then run
   the same two commands. Nothing else changes.
3. **Dense retrieval degraded (BM25 only).** The embedding model is missing from the `hf-cache` volume. Rebuild with
   network access once: `docker compose run --rm indexer`, then recreate the worker.
4. **Confirm the fix.** `fssai_index_chunks_total` shows both regulations, `fssai_retrieval_empty_total` stops climbing,
   and the §4.1 case ("source of protein") cites both regulations: `python tools/scripts/smoke.py`.
5. Write an incident entry.

**Do not** hand-edit files under `/data/index`; always rebuild from `data/corpus/raw/`.

---

## Quick reference

| Question | Where |
|---|---|
| Is the stack up and are real parts running? | `curl -s localhost:8000/readyz` |
| What happened in one run? | `GET /v1/runs/<run_id>/trace` (Jaeger link in the response) |
| Which prompt versions ran? | `prompt_versions` in the run result; `python -m fssai_prompts list` |
| Pin a prompt version while debugging | `PROMPT_CLASSIFIER_VERSION=...` / `PROMPT_RESEARCHER_VERSION=...` in `.env`, recreate the worker |
| Did the guardrail block an input? | `guardrails` in the run result: `prompt_injection:<field>/<kind>` flags |
