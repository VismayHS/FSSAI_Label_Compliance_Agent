# 307: API authentication with hashed API keys and two roles (Vismay)

- **Status:** Accepted, 2026-11-06
- **Context:** Until now `X-Client-Id` identified a caller only for rate limiting. Anyone who could reach the API
  could submit checks (each costs LLM tokens), read every run, and read the quarantine, which holds other clients'
  rejected payloads. OWASP API1, API2 and API5 all applied. Two constraints: the demo must boot from a clean clone
  with no credentials in the repo (D4, demo #1), and the web client must keep working.

## Options considered

1. **JWT / OAuth 2 with an identity provider.** The standard for public APIs, but it needs a token issuer we don't
   run, and adds the usual pitfalls (algorithm confusion, revocation). Too much for an internal tool.
2. **Static API keys in plain text in `.env`.** Simple, but a leaked `.env` or a log of it is a usable credential.
3. **API keys stored as SHA-256 hashes, each bound to a client id and a role** (chosen).

## Decision

- **The key ring.** `API_KEYS=client_id:sha256(key):role,…` in `.env`.
  - `tools/scripts/make_api_key.py` makes a 256-bit key and prints the entry.
  - Keys go in `X-API-Key` or `Authorization: Bearer`.
- **Roles.**
  - `analyst`: their own runs only.
  - `reviewer`: every run and the quarantine.
- **Identity.** With keys on, `X-Client-Id` is overwritten with the key's client id. Rate limits and feedback
  records then follow the authenticated identity.
- **Enforcement.** Everything is in one middleware: authentication, function-level and object-level checks. A
  teammate's route under `/v1/runs/{id}/…` (feedback) is covered without being edited.
- **Default.** Keys are off while `API_KEYS` is empty (the `.env.example` default). The API logs a warning when so.
- **The web client.**
  - It asks for a key only after a 401, and keeps it in `sessionStorage`.
  - With a key it polls instead of using `EventSource`, which can't send headers. A key never goes in a URL.

## Consequences

- An unknown run and another analyst's run both answer 404, so run ids can't be probed.
- With keys on, scripts need `FSSAI_API_KEY`; `smoke.py` says so on a 401.
- Load tests use one key for all simulated users. The key then fixes the client id, so raise `RATE_LIMIT_PER_MIN`
  as before.
- Rotating a key means replacing its line and recreating `api`. There is no expiry or per-key quota.
- Live updates with a key are polling (0.5–2 s), not SSE. That is what decision 301 used before SSE.
