"""Webhook callback (extra, A4): URL policy, signed delivery, bounded retries, and a run that never depends on it."""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from fssai_contracts.schemas import RunState, RunStatus, utcnow
from fssai_worker import jobs, webhook
from fssai_worker.jobs import execute_run, payload_for

from test_worker import deps, queued, request  # pytest puts this folder on sys.path

ON = {"WEBHOOK_ALLOWED_HOSTS": "hooks.example.test, Partner.Example.TEST"}


def finished(route_ok: bool = True) -> RunStatus:
    return RunStatus(run_id="run-1", state=RunState.COMPLETED if route_ok else RunState.FAILED,
                     submitted_at=utcnow(), updated_at=utcnow(), correlation_id="corr-1",
                     error=None if route_ok else "internal error (RuntimeError)")


class Recorder:
    """Stands in for httpx.post: answers from a script of status codes or exceptions."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, *, content, headers, timeout):
        self.calls.append({"url": url, "body": content, "headers": headers, "timeout": timeout})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, request=httpx.Request("POST", url))


@pytest.mark.parametrize("url, env, problem", [
    ("https://hooks.example.test/x", {}, "not enabled"),
    ("https://evil.example.test/x", ON, "not in WEBHOOK_ALLOWED_HOSTS"),
    ("ftp://hooks.example.test/x", ON, "http or https"),
    ("https://user:pw@hooks.example.test/x", ON, "credentials"),
    ("https://hooks.example.test/" + "a" * 2100, ON, "2048"),
    ("not a url", ON, "http or https"),
])
def test_only_allowed_hosts_can_receive_callbacks(url, env, problem):
    assert problem in (webhook.check_url(url, env) or "")


def test_allowed_hosts_match_case_insensitively():
    assert webhook.check_url("https://partner.example.test:8443/hook?x=1", ON) is None
    assert webhook.check_url("http://HOOKS.example.test/hook", ON) is None


def test_delivery_is_a_small_signed_json_notice():
    post = Recorder(200)
    env = {**ON, "WEBHOOK_SECRET": "s3cret"}
    assert webhook.notify("https://hooks.example.test/x", finished(), env, post=post, sleep=lambda s: None)
    [call] = post.calls
    body = json.loads(call["body"])
    assert body == {"event": "run.finished", "run_id": "run-1", "state": "completed", "route": None,
                    "complete": None, "error": None, "correlation_id": "corr-1",
                    "status_url": "/v1/runs/run-1", "trace_url": "/v1/runs/run-1/trace"}
    expected = hmac.new(b"s3cret", call["body"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-FSSAI-Signature"] == f"sha256={expected}"
    assert call["headers"]["Content-Type"] == "application/json"


def test_unsigned_without_a_secret():
    post = Recorder(204)
    webhook.notify("https://hooks.example.test/x", finished(), ON, post=post, sleep=lambda s: None)
    assert "X-FSSAI-Signature" not in post.calls[0]["headers"]


def test_retries_server_errors_and_timeouts_then_gives_up():
    post = Recorder(503, httpx.ConnectTimeout("slow"), 500)
    sleeps: list[float] = []
    assert not webhook.notify("https://hooks.example.test/x", finished(), {**ON, "WEBHOOK_MAX_ATTEMPTS": "3"},
                              post=post, sleep=sleeps.append)
    assert len(post.calls) == 3 and sleeps == [1.0, 2.0]


def test_a_client_error_is_not_retried():
    post = Recorder(404)
    assert not webhook.notify("https://hooks.example.test/x", finished(), ON, post=post, sleep=lambda s: None)
    assert len(post.calls) == 1


def test_a_host_removed_from_the_allowlist_is_never_called():
    post = Recorder(200)
    assert not webhook.notify("https://hooks.example.test/x", finished(), {}, post=post, sleep=lambda s: None)
    assert post.calls == []


def test_the_worker_notifies_after_saving_and_a_failed_callback_never_fails_the_run(monkeypatch):
    seen = []

    def fake_notify(url, status, env=None, **_):
        seen.append((url, status.state, d.run_store.get("run-1").state))  # saved before the callback
        return False                                                       # the receiver is down

    monkeypatch.setattr(jobs.webhook, "notify", fake_notify)
    d = deps()
    queued(d)
    payload = payload_for("run-1", "corr-1", request(12.0), callback_url="https://hooks.example.test/x")
    assert execute_run(payload, d) == "completed"
    assert seen == [("https://hooks.example.test/x", RunState.COMPLETED, RunState.COMPLETED)]
    assert d.run_store.get("run-1").state == RunState.COMPLETED


def test_no_callback_url_means_no_callback(monkeypatch):
    monkeypatch.setattr(jobs.webhook, "notify", lambda *a, **k: pytest.fail("called without a callback url"))
    d = deps()
    queued(d)
    assert "callback_url" not in payload_for("run-1", "corr-1", request(12.0))
    assert execute_run(payload_for("run-1", "corr-1", request(12.0)), d) == "completed"
