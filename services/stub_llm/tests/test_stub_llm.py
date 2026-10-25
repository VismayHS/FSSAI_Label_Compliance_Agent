"""The stub provider: OpenAI-compatible shape, fixtures by prompt tag, latency, faults."""
from __future__ import annotations

import json
import random
import statistics

import pytest
from fastapi.testclient import TestClient

from fssai_stub_llm.app import Settings, create_app
from fssai_stub_llm.latency import LogNormal


class NoSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def client(tmp_path=None, **settings) -> tuple[TestClient, NoSleep]:
    sleep = NoSleep()
    kwargs = {"latency_mean_s": 0, **settings}
    if tmp_path is not None:
        kwargs["fixtures_dir"] = tmp_path
    return TestClient(create_app(Settings(**kwargs), rng=random.Random(7), sleep=sleep)), sleep


def chat(c: TestClient, system: str = "You are helpful.", user: str = "hi", **extra):
    return c.post("/v1/chat/completions", json={"model": "anything", "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}], **extra})


def test_openai_compatible_response():
    c, _ = client()
    r = chat(c)
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion" and body["model"] == "anything"
    assert body["choices"][0]["message"]["role"] == "assistant" and body["choices"][0]["finish_reason"] == "stop"
    usage = body["usage"]
    assert usage["prompt_tokens"] > 0 and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_fixture_chosen_by_prompt_tag(tmp_path):
    (tmp_path / "classifier.json").write_text(json.dumps({"category": "breakfast-cereals", "claims": []}))
    (tmp_path / "classifier@v2.json").write_text(json.dumps({"content": "version two"}))
    (tmp_path / "_default.json").write_text(json.dumps({"content": "default"}))
    c, _ = client(tmp_path)
    reply = lambda s: chat(c, system=s).json()["choices"][0]["message"]["content"]  # noqa: E731
    assert json.loads(reply("[prompt:classifier@v1] Classify.")) == {"category": "breakfast-cereals", "claims": []}
    assert reply("[prompt:classifier@v2] Classify.") == "version two"
    assert reply("[prompt:researcher@v1] Research.") == "default"
    assert reply("no tag here") == "default"


def test_json_mode_gets_json_even_from_a_text_fixture():
    c, _ = client()
    content = chat(c, system="[prompt:x@1] s", response_format={"type": "json_object"}).json()["choices"][0]["message"]["content"]
    assert json.loads(content)["stub"] is True


def test_latency_is_drawn_and_awaited():
    c, sleep = client(latency_mean_s=1.5, latency_p95_s=4)
    for _ in range(5):
        chat(c)
    assert len(sleep.calls) == 5 and all(s > 0 for s in sleep.calls)


def test_lognormal_matches_mean_and_p95():
    dist = LogNormal.from_mean_p95(1.5, 4.0)
    assert dist.mean == pytest.approx(1.5) and dist.p95 == pytest.approx(4.0)
    rng = random.Random(1)
    draws = sorted(dist.sample(rng) for _ in range(40000))
    assert statistics.mean(draws) == pytest.approx(1.5, rel=0.05)
    assert draws[int(0.95 * len(draws))] == pytest.approx(4.0, rel=0.05)
    assert LogNormal.from_mean_p95(0, 4) is None
    capped = LogNormal.from_mean_p95(1.0, 50.0)  # unreachable ratio: sigma capped, still a valid distribution
    assert capped.sigma == pytest.approx(1.6448536269514722)


def test_down_answers_503_and_can_be_toggled_at_runtime():
    c, _ = client(down="1")
    assert chat(c).status_code == 503
    assert c.post("/admin/faults", json={"down": "0"}).json()["down"] == "0"
    assert chat(c).status_code == 200
    assert c.get("/readyz").status_code == 200  # never unhealthy because of an injected fault


def test_hang_waits_then_fails():
    c, sleep = client(down="hang", hang_s=300)
    assert chat(c).status_code == 503 and sleep.calls == [300]


def test_failure_and_rate_limit_rates():
    c, _ = client(fail_rate=1.0)
    assert chat(c).status_code == 500
    c, _ = client(rate_limit_rate=1.0)
    r = chat(c)
    assert r.status_code == 429 and r.headers["retry-after"] == "1"
    c, _ = client(fail_rate=0.3)
    codes = [chat(c).status_code for _ in range(300)]
    assert 0.2 < codes.count(500) / len(codes) < 0.4


def test_metrics_and_models():
    c, _ = client()
    chat(c, system="[prompt:verifier@v1] check")
    text = c.get("/metrics").text
    assert 'fssai_stub_requests_total{outcome="ok",prompt="verifier"}' in text
    assert c.get("/v1/models").json()["data"][0]["id"] == "stub"
    assert c.get("/healthz").json() == {"status": "ok"}


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("STUB_LATENCY_MEAN_S", "2")
    monkeypatch.setenv("STUB_LATENCY_P95_S", "5  # comment")
    monkeypatch.setenv("STUB_DOWN", "1")
    s = Settings.from_env()
    assert (s.latency_mean_s, s.latency_p95_s, s.down) == (2.0, 5.0, "1")
