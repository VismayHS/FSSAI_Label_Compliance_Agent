# 301 · Async runs: return a run id at once, the client polls

**Status:** accepted · **Owner:** Vismay · **Requirements:** A4, A8, D6

## Context
A run makes several LLM and tool calls and takes tens of seconds (spec §6, A4). Holding an HTTP request
open that long ties up API workers, breaks behind proxies with 30–60 s idle timeouts, and loses the
result if the connection drops. A4 asks us to return a run identifier immediately and either let the
caller poll or call it back, and to justify the choice.

## Options
1. **Polling:** `POST /v1/runs` → `202 {run_id, status_url}`; the caller polls `GET /v1/runs/{id}`.
2. **Callback (webhook):** the caller registers a URL; we `POST` the result when done.
3. **Server-sent events / WebSocket:** the caller holds a stream open for progress.

## Decision
Polling is the contract (option 1). A callback is a later extra on top of it, not a replacement.

- Every client can poll: the web client, Locust, curl, the eval runner. A webhook needs the caller to
  run a reachable HTTP server, which a browser page, a load generator and a CLI don't have.
- Polling is stateless on the server: any API replica can answer, nothing to retry when a callback
  target is down, no outbound network from our containers to arbitrary URLs (an SSRF risk).
- D6 measures a run "from submission to final result". Polling gives Locust that end time directly.
- Cost is small: a poll is one key lookup. The web client polls with backoff (0.5 s → 2 s).

## Consequences
- Clients must handle `queued` and `running` and stop at `completed` / `failed`.
- `202` carries `Location` and `status_url`, plus `trace_url` for the full reconstruction (D5).
- Extras later: SSE progress for the web client, an optional `callback_url` (validated against an
  allowlist) for system-to-system callers.
