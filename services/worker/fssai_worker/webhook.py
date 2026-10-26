"""Webhook callback (extra, A4): when a run finishes, POST a small JSON notice to the URL its caller gave.

The caller sends `X-Callback-Url` with `POST /v1/runs`; the API checks it with `check_url` before accepting the
run, and the worker calls `notify` after the final state is saved. Rules:
- off unless WEBHOOK_ALLOWED_HOSTS lists hosts: the worker never calls a host nobody allowed (SSRF);
- signed with HMAC-SHA256 of the body when WEBHOOK_SECRET is set (`X-FSSAI-Signature: sha256=<hex>`);
- bounded: WEBHOOK_TIMEOUT_S per attempt, WEBHOOK_MAX_ATTEMPTS attempts with backoff, client errors not retried;
- the notice carries ids, state and route only, never label text; a failed callback never changes the run.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

import httpx

from fssai_contracts.schemas import RunStatus

MAX_URL = 2048


def _env(env: Mapping[str, str], name: str, default: str = "") -> str:
    return env.get(name, default).split("#", 1)[0].strip() or default


def allowed_hosts(env: Mapping[str, str]) -> set[str]:
    return {h.strip().lower() for h in _env(env, "WEBHOOK_ALLOWED_HOSTS").split(",") if h.strip()}


def check_url(url: str, env: Mapping[str, str] = os.environ) -> str | None:
    """None if the worker may call this URL, else why not (shown to the caller as a 400)."""
    hosts = allowed_hosts(env)
    if not hosts:
        return "Callbacks are not enabled on this service (WEBHOOK_ALLOWED_HOSTS is empty)."
    if len(url) > MAX_URL:
        return f"X-Callback-Url is longer than {MAX_URL} characters."
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "X-Callback-Url must be an absolute http or https URL."
    if parts.username or parts.password:
        return "X-Callback-Url must not carry credentials; use WEBHOOK_SECRET signing instead."
    if parts.hostname.lower() not in hosts:
        return f"Host '{parts.hostname}' is not in WEBHOOK_ALLOWED_HOSTS."
    return None


def notice(status: RunStatus) -> dict:
    result = status.result
    return {"event": "run.finished", "run_id": status.run_id, "state": status.state.value,
            "route": result.routing.route.value if result else None,
            "complete": result.complete if result else None, "error": status.error,
            "correlation_id": status.correlation_id,
            "status_url": f"/v1/runs/{status.run_id}", "trace_url": f"/v1/runs/{status.run_id}/trace"}


def notify(url: str, status: RunStatus, env: Mapping[str, str] = os.environ, *,
           post: Callable[..., httpx.Response] = httpx.post, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Deliver the notice. True on a 2xx; False after the last failed attempt. Never raises."""
    if check_url(url, env):  # the allowlist may have changed since the run was accepted
        return False
    body = json.dumps(notice(status), separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "fssai-label-agent/0.1",
               "X-Correlation-Id": status.correlation_id or status.run_id}
    secret = _env(env, "WEBHOOK_SECRET")
    if secret:
        headers["X-FSSAI-Signature"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    attempts = max(1, int(float(_env(env, "WEBHOOK_MAX_ATTEMPTS", "3"))))
    timeout = float(_env(env, "WEBHOOK_TIMEOUT_S", "5"))
    for attempt in range(1, attempts + 1):
        try:
            response = post(url, content=body, headers=headers, timeout=timeout)
            if response.is_success:
                return True
            if response.status_code < 500 and response.status_code != 429:
                return False  # the receiver refused it; retrying sends the same thing
        except httpx.HTTPError:
            pass
        if attempt < attempts:
            sleep(float(2 ** (attempt - 1)))
    return False
