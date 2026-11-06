# API and web security

Owner: Vismay. Code: `apps/api/app/security.py` (API), `apps/web/nginx.conf` + `apps/web/security-headers.conf` (web),
`apps/web/src/lib/apiKey.ts` (client). Tests: `apps/api/tests/test_security.py`, `apps/web/src/App.test.tsx`
("API keys"). Decision record [307](decisions/307-vismay-api-keys.md).

Built against the **OWASP API Security Top 10 (2023)**, with the
[shieldfy API Security Checklist](https://github.com/shieldfy/API-Security-Checklist) and the
[security guide for developers](https://github.com/FallibleInc/security-guide-for-developers) as checklists. The
lists are written for public internet APIs; this is a service for an internal analyst team, so each item below says
what we did, or why it does not apply.

## Switching it on

```bash
python tools/scripts/make_api_key.py analyst-1                  # an analyst: their own checks only
python tools/scripts/make_api_key.py lead --role reviewer       # a reviewer: every check, the quarantine
# put the printed API_KEYS entries, comma-separated, in .env (only SHA-256 hashes go there), then:
docker compose up -d --force-recreate api
```

- **Web client:** the first call the API refuses shows a key box at the top of the page. The key stays in
  `sessionStorage` for that tab only.
- **Scripts** (`smoke.py`, the demo tools, Locust): they send `FSSAI_API_KEY` from the shell.
- **`curl`:** `-H "X-API-Key: <key>"`, or `Authorization: Bearer <key>`.

With `API_KEYS` empty the API is open and logs `api_auth_disabled` at start-up. That is the default in
`.env.example`, so a clean clone boots and serves a request with no credentials in the repo (D4, demo #1).

## OWASP API Security Top 10 (2023)

| Risk | What we do | Where / evidence |
|---|---|---|
| **API1** Broken object-level authorisation | A run belongs to the client that submitted it. An analyst key asking for another client's run, its trace, its events or its feedback gets **404, the same answer as an unknown id**, so run ids can't be probed. The check is one rule in the middleware for every `/v1/runs/{id}/…` route, including routes added later. `GET /v1/runs` lists only the caller's runs. Run ids are random 128-bit (`uuid4`), never sequential. | `security.py` `_authorise`; `test_another_analysts_run_is_not_found`, `test_listing_shows_an_analyst_only_their_own_runs` |
| **API2** Broken authentication | API keys of 256 random bits. The server stores only SHA-256 hashes and compares in constant time. Keys are accepted only in a header, never in a URL; the web client polls instead of using `EventSource` when it has a key, because `EventSource` can't send headers. Refusals are a 401 with `WWW-Authenticate`, logged (`auth_refused`) and counted (`fssai_auth_failures_total`) without the key. A malformed `API_KEYS` stops the API at start-up instead of leaving it open. | `KeyRing`; `test_the_key_never_appears_in_responses_or_logs`, `test_a_malformed_key_ring_fails_at_start_up` |
| **API3** Broken object-property-level authorisation | Responses are typed Pydantic models; nothing is serialised from a raw database row. Requests: the gate rejects unknown fields (`unknown_field`, demo #4), so a caller can't set `run_id`, `client_id` or `state`. | `apps/api/app/models.py`, the data contract (`docs/data-contract.md`) |
| **API4** Unrestricted resource consumption | Several limits: per-client rate limit at the gate (D7); per-IP limit at the web proxy (10 r/s, burst 40); body size limits (API 256 KiB, nginx 300 KiB); list pages capped at 100; the run itself bounded in steps, tool calls and wall time (decision 306); SSE streams closed after the run deadline. With keys on, `X-Client-Id` comes from the key, so a caller can't rotate client ids to escape its rate limit. | `test_client_id_comes_from_the_key_not_the_header`; nginx `limit_req` (measured: 18 of 120 parallel requests got 429) |
| **API5** Broken function-level authorisation | Two roles. `/v1/quarantine` holds other clients' rejected payloads, so it is reviewer-only (403 for an analyst). | `test_quarantine_is_reviewer_only` |
| **API6** Unrestricted access to sensitive business flows | The one costly flow is a check (LLM tokens). It is rate-limited per client and per IP, and a malformed request never reaches the LLM (gate before enqueue, D1). | `fssai_gate`, demo #4 |
| **API7** Server-side request forgery | The only outbound call a client can trigger is the optional webhook (`X-Callback-Url`). Its host must be in `WEBHOOK_ALLOWED_HOSTS`; it is off while that is empty, and each callback is signed (`X-FSSAI-Signature`). | `fssai_worker.webhook.check_url` |
| **API8** Security misconfiguration | API responses: `nosniff`, `X-Frame-Options: DENY`, CSP `default-src 'none'`, `Referrer-Policy: no-referrer`, COOP/CORP same-origin, `Cache-Control: no-store` on `/v1`, no `Server` header (uvicorn `--no-server-header`). Errors: a JSON problem with a correlation id, never a stack trace. `/docs` can be turned off (`API_DOCS_ENABLED=0`). No CORS headers at all: the browser reaches the API through the same origin. Web: a strict CSP (`script-src 'self'`, no inline script, no third-party origin), `server_tokens off`. Containers run as non-root users. | `test_security_headers_on_api_responses`, `test_unexpected_errors_never_leak_a_stack_trace`; `curl -I` output in the 6 Nov log |
| **API9** Improper inventory management | One version (`/v1`), published as OpenAPI with the key scheme declared. The routes are listed in `LLM_Context.md` §7, and a test pins the router list. | `test_openapi_publishes_the_key_scheme`, `test_ops.py` |
| **API10** Unsafe consumption of APIs | The LLM provider's output is treated as untrusted. Every quote must be verbatim in a passage retrieved in this run (grounding, verifier). The output filter blocks approval wording. Label text is screened for injection before any model call (L4). Provider calls have timeouts, bounded retries and a circuit breaker (A5). | `fssai_guardrails`, `fssai_verification`, `fssai_llm_gateway` |

## Checklist items that apply differently here

- **HTTPS / HSTS.** The stack serves plain HTTP on localhost for the demo. In a deployment, TLS terminates at the
  organisation's reverse proxy in front of `web`. HSTS is set there, not by us, because sending it over plain HTTP
  is ignored.
- **OAuth / JWT.** Not used. An internal team of analysts with per-person keys needs no token issuer, and API keys
  avoid JWT's well-known pitfalls (`alg: none`, weak secrets, no revocation). Revoking a key means removing its line
  from `API_KEYS`. With SSO, the reverse proxy would authenticate and pass an identity header.
- **Secrets.** Credentials, endpoints and model ids live only in `.env`, which git ignores (D4). The audit
  `tools/scripts/audit_secrets.py` fails CI on any provider key, on this service's own `fssai_…` keys and on a
  filled-in `API_KEYS` in a tracked file.
- **Logging.** JSON logs with a correlation id on every request. Auth refusals are logged with the reason, path and
  client IP, never the key. Label text is never logged by the API.
- **Input.** All label fields are untrusted: validated at the gate, rendered as text (never HTML) in the web client,
  screened for prompt injection before any model sees them.
