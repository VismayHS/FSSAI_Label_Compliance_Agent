# 2026-10-30: the eval comparison ran into Groq's daily token cap after 16 runs

- **Author:** Vismay · **Severity:** stopped the L2/L3 prompt comparison partway; would stop any demo rehearsal done after a long eval session on the same key
- **Component:** the Groq free tier behind `packages/llm_gateway`; the eval runner (`python -m fssai_agents.compare run`)

## What happened

The researcher 1.0.0 vs 1.1.0 comparison (30 scenarios per variant, 60 s apart, `RUN_MAX_WALL_S=180`) ran its first
16 scenarios to completion in 17-52 s each. From the 17th on, every scenario ended `complete=false` and was marked
`429` by the runner, after only the classifier call had succeeded. The researcher's first call failed with
*"primary: HTTP 429 after 1 attempt(s); fallback: HTTP 429 after 4 attempt(s)"*.

## How it was noticed

The runner prints `429` instead of `ok` for a run that ended on a provider failure. Four in a row, all at the same
step, did not look like the per-minute limit from incident `2026-10-26-vismay-groq-free-tier-rate-limit`.

## Cause

- A one-token request still succeeded, and its headers showed the per-minute budget nearly full
  (`x-ratelimit-remaining-tokens: 6898` of 8000) and 946 of 1,000 daily requests left. Nothing in the headers
  pointed at a daily token limit.
- A request of about 5,000 tokens answered `429` with `retry-after: 1022` and the body *"Rate limit reached for model
  ... on tokens per day (TPD): Limit 200000, Used 197292, Requested 5073"*.
- So each model has a third limit, **200,000 tokens a day**, which only a large enough request reveals. At about
  12,500 tokens per run that is about 16 runs a day per key. The 16 completed runs, plus the day's earlier checks, had used it up.
- The gateway behaved as designed: the `retry-after` (17 minutes) was longer than the run had left, so it stopped at
  once instead of waiting. The fallback model then hit its own per-minute limit and gave up after 4 attempts.

## Fix

- Stopped the comparison. The runner keeps every scored row and re-runs only the `429` rows when resumed
  (`--resume`), so nothing was lost.
- Wrote the daily cap into `docs/contexts/LLM_Context.md` §4 so nobody plans an eval run or rehearsal as one sitting.
- Decision 306 raises the run bound to 180 s on the real provider (one per-minute refill plus the slowest run). That
  is why all 16 runs before the cap completed, including the §4.1 case that timed out at 90 s on 27 Oct.

## Lesson

A free tier's limits are not all in its response headers. Probe with a request the size of a real one, not a one-token
ping. Then budget real-LLM work in runs per day, not just per minute: the eval set, the comparison and two demo
rehearsals do not fit into one day on one key.
