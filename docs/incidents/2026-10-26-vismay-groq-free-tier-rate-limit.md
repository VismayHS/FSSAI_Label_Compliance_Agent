# 2026-10-26: back-to-back real runs hit Groq's free-tier token limit and ended incomplete

- **Author:** Vismay · **Severity:** would have broken any demo or eval run made in quick succession; found the day the real LLM was switched on
- **Component:** `libs/llm_gateway` (and every run that uses the real provider)

## What happened

The first real runs on Groq (a large open-weight model as primary and a smaller one as fallback, through the gateway)
worked one at a time. A run started a few seconds after another ended with `complete=false` and
`regulatory-review`: *"ProviderUnavailable: primary: HTTP 400 (not retried) after 4 attempt(s); fallback: HTTP 400
(not retried) after 1 attempt(s)"*. The researcher's fourth LLM call failed; the three before it had succeeded.

## How it was noticed

Testing the webhook extra: the signed run-finished notice arrived with `"complete": false`, although the request
was the same as a run that had just completed.

## Cause

- The worker's log showed three `llm_retry` events with reason `HTTP 429` before the 400.
- Groq's own response headers on a one-token request: `x-ratelimit-limit-tokens: 8000` per model, refilled each
  minute, and `x-ratelimit-limit-requests: 1000` per day.
- One §4.1 run uses about 8,000 to 12,500 tokens (5 LLM calls). A single run can use a whole minute's budget, so a
  second run started straight after it is rate-limited partway through.
- Why the last answer was a 400 rather than another 429 could not be told: the gateway recorded only `HTTP 400`,
  dropping the provider's error code.

## Fix

- The gateway now records the provider's error `type/code` (never its message, which can echo label text or name the
  model id), so the next such failure says what it was.
- A `json_validate_failed` 400 (the model's own output was not valid JSON in JSON mode) is now retried like a
  malformed reply instead of failing the run. Tests in `libs/llm_gateway/tests/test_client.py`.
- Operating rule for the team: with the free tier, run real-LLM checks **one at a time**, about a minute apart, and
  plan the eval set accordingly (30 scenarios take over half an hour per prompt variant). The fallback model has its
  own 8,000-token bucket, so it is real extra capacity, not only a degradation path.

## Lesson

Read a provider's limits from its response headers before planning work against it, and never throw away an error
code: "HTTP 400" alone turned a ten-second diagnosis into guesswork.
