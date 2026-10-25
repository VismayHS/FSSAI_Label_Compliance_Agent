"""Locust load test for complete runs (D6, A7; loadtest/SLO.md).

Each simulated analyst submits a label check, polls until the run reaches a terminal state, and
reports the whole thing as one request named `full_run` (type RUN): from just before the POST to the
poll that sees `completed`/`failed`. That is the SLI in SLO.md; the POST alone says nothing about it.

    locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 5 -r 5 --run-time 5m
    python loadtest/run_matrix.py ...          # the 1/2/5/10/20-user matrix, both worker scales

Environment:
    LOADTEST_PAYLOADS     glob of request bodies   (default loadtest/payloads/*.json)
    LOADTEST_POLL_S       poll interval, s          (default 0.5; SLO.md allows for it)
    LOADTEST_RUN_TIMEOUT_S  give up and count a failure after this long (default 180)
    LOADTEST_THINK_S      pause between a user's runs, s (default 0: closed loop)
    LOADTEST_OUTCOMES     write per-route counts and run ids here as JSON at the end (optional)
"""
from __future__ import annotations

import glob
import json
import os
import random
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

from locust import HttpUser, constant, events, task

HERE = Path(__file__).resolve().parent
PAYLOADS = [json.loads(Path(p).read_text(encoding="utf-8"))
            for p in sorted(glob.glob(os.environ.get("LOADTEST_PAYLOADS", str(HERE / "payloads" / "*.json"))))]
POLL_S = float(os.environ.get("LOADTEST_POLL_S", "0.5"))
RUN_TIMEOUT_S = float(os.environ.get("LOADTEST_RUN_TIMEOUT_S", "180"))
THINK_S = float(os.environ.get("LOADTEST_THINK_S", "0"))
TERMINAL = {"completed", "failed"}

_outcomes: Counter = Counter()
_lock = threading.Lock()

if not PAYLOADS:
    raise SystemExit("no load-test payloads found (LOADTEST_PAYLOADS)")


class Analyst(HttpUser):
    wait_time = constant(THINK_S)

    def on_start(self) -> None:
        # One client id per simulated analyst, so per-client rate limits (D7) apply per user as in real use.
        self.client_id = f"locust-{uuid.uuid4().hex[:10]}"

    @task
    def full_run(self) -> None:
        payload = random.choice(PAYLOADS)
        headers = {"X-Client-Id": self.client_id, "X-Correlation-Id": f"lt-{uuid.uuid4().hex[:16]}"}
        t0 = time.perf_counter()
        with self.client.post("/v1/runs", json=payload, headers=headers, name="POST /v1/runs",
                              catch_response=True) as resp:
            if resp.status_code != 202:
                resp.failure(f"HTTP {resp.status_code}")
                self._report(t0, f"submit rejected: HTTP {resp.status_code}", route="none")
                return
            run_id = resp.json()["run_id"]
            resp.success()

        state, body = None, {}
        while time.perf_counter() - t0 < RUN_TIMEOUT_S:
            time.sleep(POLL_S)  # locust patches time.sleep under gevent
            with self.client.get(f"/v1/runs/{run_id}", name="GET /v1/runs/{id}", catch_response=True) as poll:
                if poll.status_code != 200:
                    poll.failure(f"HTTP {poll.status_code}")
                    continue
                body = poll.json()
                state = body.get("state")
                poll.success()
            if state in TERMINAL:
                break
        result = body.get("result") or {}
        route = (result.get("routing") or {}).get("route", "none")
        if state == "completed":
            self._report(t0, None, route=route, complete=result.get("complete"))
        else:
            self._report(t0, f"run {run_id} ended {state or f'not finished after {RUN_TIMEOUT_S:g}s'}", route=route)

    def _report(self, t0: float, error: str | None, *, route: str, complete: bool | None = None) -> None:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        with _lock:
            _outcomes[f"route={route}"] += 1
            _outcomes[f"complete={complete}"] += 1
            _outcomes["error" if error else "ok"] += 1
        self.environment.events.request.fire(
            request_type="RUN", name="full_run", response_time=elapsed_ms, response_length=0,
            exception=Exception(error) if error else None, context={"route": route})


@events.test_stop.add_listener
def _write_outcomes(environment, **_kwargs) -> None:
    out = os.environ.get("LOADTEST_OUTCOMES")
    if out:
        Path(out).write_text(json.dumps(dict(_outcomes), indent=2, sort_keys=True), encoding="utf-8")
