"""API security: authentication, object- and function-level authorisation, security headers (docs/security.md).

Mapped to the OWASP API Security Top 10 (2023):

- API2 broken authentication: API keys in `X-API-Key` (or `Authorization: Bearer`). The server keeps only their
  SHA-256 hashes (`API_KEYS`), compares in constant time, and logs and counts failures without the key.
- API1 broken object-level authorisation: a run belongs to the client that submitted it. Another analyst's run id
  answers 404, exactly like an unknown id, so ids can't be probed. Applies to every `/v1/runs/{id}/...` route,
  including ones added later (feedback), because it is enforced here, not in each route.
- API5 broken function-level authorisation: `reviewer` keys see every run and the quarantine; `analyst` keys see
  their own runs only. `/v1/quarantine` holds other clients' rejected payloads, so it is reviewer-only.
- API4 unrestricted resource consumption: with keys on, `X-Client-Id` is set from the key, so a caller can't rotate
  client ids to escape the per-client rate limit (the gate's limiter, D7).
- API8 security misconfiguration: security headers on every response, `Cache-Control: no-store` on API data,
  no stack traces in errors, the interactive docs switchable off (`API_DOCS_ENABLED=0`).

With `API_KEYS` empty the API is open, as on a developer laptop and in a clean clone (the demo must boot from
`.env.example`, which holds no credentials, D4). The API logs a warning at start-up when that is so.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from prometheus_client import Counter

from .observability import event

ROLES = ("analyst", "reviewer")
_CLIENT = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_PATH = re.compile(r"^/v1/runs/([0-9a-f]{32})(?:/|$)")
REVIEWER_ONLY = ("/v1/quarantine",)
# Not behind a key: liveness/readiness for Compose and load balancers, the Prometheus scrape (not proxied by the
# web server), and the published contract (F1). The interactive docs are governed by API_DOCS_ENABLED instead.
PUBLIC_PREFIXES = ("/healthz", "/readyz", "/metrics", "/openapi.json", "/docs", "/redoc")

AUTH_FAILURES = Counter("fssai_auth_failures_total", "Requests refused by API authentication or authorisation",
                        ["reason"])

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# JSON never needs to run or load anything. The Swagger page does (its own CDN script), so it keeps FastAPI's.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Principal:
    client_id: str
    role: str = "analyst"

    @property
    def reviewer(self) -> bool:
        return self.role == "reviewer"


class KeyRing:
    """The API keys this deployment accepts, as `client_id:sha256(key)[:role]` entries."""

    def __init__(self, entries: dict[str, Principal] | None = None) -> None:
        self._entries = dict(entries or {})

    @classmethod
    def parse(cls, raw: str) -> KeyRing:
        """Fail fast on a malformed entry: a typo must not silently leave the API open or lock everyone out."""
        entries: dict[str, Principal] = {}
        for item in filter(None, (p.strip() for p in raw.split("#", 1)[0].split(","))):
            parts = item.split(":")
            if len(parts) not in (2, 3):
                raise ValueError(f"API_KEYS entry {parts[0]!r}...: expected client_id:sha256[:role]")
            client, digest, role = parts[0], parts[1].lower(), (parts[2] if len(parts) == 3 else "analyst")
            if not _CLIENT.match(client):
                raise ValueError(f"API_KEYS: client id {client!r} must be 1-64 letters, digits or . _ - (no ':')")
            if not _SHA256.match(digest):
                raise ValueError(f"API_KEYS entry for {client!r}: the key must be given as its 64-hex SHA-256 "
                                 "(python tools/scripts/make_api_key.py), never in plain text")
            if role not in ROLES:
                raise ValueError(f"API_KEYS entry for {client!r}: role must be one of {', '.join(ROLES)}")
            entries[digest] = Principal(client, role)
        return cls(entries)

    @classmethod
    def from_env(cls, environ: dict[str, str]) -> KeyRing:
        return cls.parse(environ.get("API_KEYS", ""))

    @property
    def enabled(self) -> bool:
        return bool(self._entries)

    def authenticate(self, presented: str | None) -> Principal | None:
        if not presented:
            return None
        digest = hash_key(presented)
        found = None
        for stored, principal in self._entries.items():  # constant time per entry; no early exit on a match
            if hmac.compare_digest(stored, digest):
                found = principal
        return found


def presented_key(request: Request) -> str | None:
    key = request.headers.get("X-API-Key")
    if key:
        return key.strip()
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _problem(request: Request, status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail, "correlation_id": getattr(request.state, "correlation_id", None)},
                        status_code=status, headers=headers)


def _set_client_id(request: Request, client_id: str) -> None:
    """Every route reads X-Client-Id (rate limit, feedback, quarantine records). With keys on, it is the key's
    identity, whatever the caller sent."""
    headers = [(k, v) for k, v in request.scope["headers"] if k != b"x-client-id"]
    headers.append((b"x-client-id", client_id.encode("ascii")))
    request.scope["headers"] = headers


def visible_to(principal: Principal | None, owner: str | None) -> bool:
    """Whether a run submitted by `owner` may be shown. No principal means keys are off: everything is visible."""
    return principal is None or principal.reviewer or owner == principal.client_id


def install(app: FastAPI, keyring: KeyRing) -> None:
    """Add before observability.install, so this runs inside the correlation middleware (refusals carry an id)."""
    if not keyring.enabled:
        event("api_auth_disabled", detail="API_KEYS is empty: every /v1 route is open. Set it outside development.")

    build_openapi = app.openapi

    def openapi():  # publish the scheme, so /docs offers "Authorize" and clients know what to send
        if app.openapi_schema:
            return app.openapi_schema
        schema = build_openapi()
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKey"] = {
            "type": "apiKey", "in": "header", "name": "X-API-Key",
            "description": "Required on every /v1 route when the deployment sets API_KEYS (docs/security.md)."}
        if keyring.enabled:
            for path, operations in schema.get("paths", {}).items():
                if path.startswith("/v1/"):
                    for operation in operations.values():
                        operation.setdefault("security", [{"ApiKey": []}])
        return schema

    app.openapi = openapi

    @app.middleware("http")
    async def secure(request: Request, call_next):
        request.state.principal = None
        path = request.url.path
        if keyring.enabled and path.startswith("/v1/") and request.method != "OPTIONS":
            refusal = await _authorise(request, path)
            if refusal is not None:
                return _headers(path, refusal)
        return _headers(path, await call_next(request))

    async def _authorise(request: Request, path: str):
        principal = keyring.authenticate(presented_key(request))
        if principal is None:
            reason = "missing" if presented_key(request) is None else "invalid"
            AUTH_FAILURES.labels(reason).inc()
            event("auth_refused", correlation_id=request.state.correlation_id, reason=reason, path=path,
                  client_ip=request.client.host if request.client else None)
            return _problem(request, 401, "An API key is required: send it in the X-API-Key header.",
                            {"WWW-Authenticate": 'ApiKey header="X-API-Key"'})
        request.state.principal = principal
        _set_client_id(request, principal.client_id)
        if path.startswith(REVIEWER_ONLY) and not principal.reviewer:
            AUTH_FAILURES.labels("forbidden").inc()
            event("auth_forbidden", correlation_id=request.state.correlation_id, client_id=principal.client_id,
                  path=path)
            return _problem(request, 403, "This needs a reviewer key.")
        run = _RUN_PATH.match(path)
        if run and not principal.reviewer:
            status = await run_in_threadpool(request.app.state.run_store.get, run.group(1))
            if status is not None and not visible_to(principal, status.client_id):
                AUTH_FAILURES.labels("not_owner").inc()
                event("auth_not_owner", correlation_id=request.state.correlation_id, client_id=principal.client_id,
                      run_id=run.group(1))
                return _problem(request, 404, "No run with this id.")  # same answer as an unknown id
        return None

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):  # never a stack trace or exception text to the caller
        event("http_unhandled_error", correlation_id=getattr(request.state, "correlation_id", None),
              path=request.url.path, error_type=type(exc).__name__)
        return _problem(request, 500, "Internal error. Quote the correlation id when reporting it.")


def _headers(path: str, response):
    for name, value in _HEADERS.items():
        response.headers.setdefault(name, value)
    if not path.startswith(("/docs", "/redoc")):
        response.headers.setdefault("Content-Security-Policy", _API_CSP)
    if path.startswith("/v1/"):
        response.headers.setdefault("Cache-Control", "no-store")  # run data never sits in a cache (SSE: no-cache)
    return response
