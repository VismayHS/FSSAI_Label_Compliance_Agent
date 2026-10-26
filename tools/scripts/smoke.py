"""Smoke test of a running stack (make smoke; demo #1): the system boots and serves a valid request.

    python tools/scripts/smoke.py [--base-url http://localhost:8000] [--timeout 300] [--expect-route ROUTE]

Checks, in order:
  1. /readyz turns ready (queue and run store reachable),
  2. a §4.1-style request ("Source of protein", 8 g per 100 g) is accepted with 202 and finishes,
  3. its result has a route, the not-an-approval notice, and a trace with steps and the request,
  4. a malformed request is rejected with 422 and a quarantine id, and creates no run (D1, demo #4).
Standard library only, so it runs on Windows and macOS with any Python 3.11+. Exit 0 = all passed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTES = {"clear-for-print", "revise-and-recheck", "regulatory-review"}


def category() -> str:
    """The first CORPUS_CATEGORIES entry from .env, so the request is in scope for this stack."""
    for name in (".env", ".env.example"):
        path = ROOT / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("CORPUS_CATEGORIES="):
                    value = line.split("=", 1)[1].split("#", 1)[0].strip()
                    if value:
                        return value.split(",")[0].strip()
    return "breakfast-cereals"


def request_body() -> dict:
    return {
        "declared_category": category(),
        "package": {"net_quantity": 500, "net_quantity_unit": "g", "principal_display_panel_cm2": 180},
        "label": {"product_name": "Multigrain flakes", "brand_name": "Smoke Test", "claims": ["Source of protein"],
                  "front_of_pack_text": "Source of protein", "ingredients": "Wheat, oats, rice, sugar, salt",
                  "allergen_statement": "Contains: wheat, oats", "veg_status": "veg"},
        "nutrition": {"basis": "per_100g", "energy_kcal": 371, "protein_g": 8, "carbohydrate_g": 78,
                      "total_sugars_g": 12, "total_fat_g": 3},
    }


def call(method: str, url: str, body: dict | None = None, client: str = "smoke") -> tuple[int, dict, Message]:
    """(status, JSON body, headers). Header lookups ignore case, as HTTP requires."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Client-Id": client})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}"), resp.headers
    except urllib.error.HTTPError as err:
        payload = err.read()
        try:
            parsed = json.loads(payload or b"{}")
        except ValueError:
            parsed = {"raw": payload[:300].decode("utf-8", "replace")}
        return err.code, parsed, err.headers


class Failed(Exception):
    pass


def check(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)
    print(f"  ok  {what}")


def wait_ready(base: str, deadline: float) -> None:
    last = "no answer"
    while time.monotonic() < deadline:
        try:
            status, body, _ = call("GET", f"{base}/readyz")
            if status == 200 and body.get("ready"):
                check(True, "API ready: " + "; ".join(f"{k}: {v['detail']}" for k, v in body["checks"].items()))
                return
            last = json.dumps(body.get("checks", body))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            last = str(exc)
        time.sleep(2)
    raise Failed(f"API not ready before the timeout; last answer: {last}")


def run(base: str, timeout: float, expect_route: str | None) -> None:
    deadline = time.monotonic() + timeout
    wait_ready(base, deadline)
    client = f"smoke-{uuid.uuid4().hex[:8]}"

    status, accepted, headers = call("POST", f"{base}/v1/runs", request_body(), client)
    check(status == 202 and len(accepted.get("run_id", "")) == 32, f"valid request accepted (202, run {accepted.get('run_id')})")
    check(headers.get("Location") == accepted["status_url"], "Location header points at the status URL")

    delay, state, run_status = 0.5, "queued", {}
    while time.monotonic() < deadline:
        _, run_status, _ = call("GET", f"{base}{accepted['status_url']}", client=client)
        state = run_status.get("state", "?")
        if state in ("completed", "failed"):
            break
        time.sleep(delay)
        delay = min(delay * 1.5, 3)
    check(state == "completed", f"run finished as '{state}'" + (f": {run_status.get('error')}" if state == "failed" else ""))
    result = run_status["result"]
    route = result["routing"]["route"]
    check(route in ROUTES, f"routed to '{route}' ({result['routing']['reason']})")
    if expect_route:
        check(route == expect_route, f"route is the expected '{expect_route}'")
    check("not an approval" in result["notice"], "result carries the not-an-approval notice")
    check(run_status.get("correlation_id") == accepted["correlation_id"], "correlation id carried onto the run")

    _, trace, _ = call("GET", f"{base}{accepted['trace_url']}", client=client)
    check(bool(trace.get("steps")) and trace.get("request") is not None,
          f"trace reconstructs the run ({len(trace.get('steps', []))} steps)")

    _, before, _ = call("GET", f"{base}/v1/runs?limit=100", client=client)
    status, rejected, _ = call("POST", f"{base}/v1/runs", {"declared_category": category()}, client)
    _, after, _ = call("GET", f"{base}/v1/runs?limit=100", client=client)
    check(status == 422 and bool(rejected.get("quarantine_id")) and bool(rejected.get("errors")),
          f"malformed request rejected (422, {len(rejected.get('errors', []))} field errors, quarantined)")
    check(len(after) == len(before), "the rejected request started no run")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=300, help="seconds for readiness plus the run")
    parser.add_argument("--expect-route", choices=sorted(ROUTES))
    args = parser.parse_args()
    print(f"smoke test against {args.base_url}")
    try:
        run(args.base_url.rstrip("/"), args.timeout, args.expect_route)
    except Failed as exc:
        print(f"  FAIL {exc}")
        return 1
    except (urllib.error.URLError, OSError) as exc:
        print(f"  FAIL cannot reach {args.base_url}: {exc}")
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
