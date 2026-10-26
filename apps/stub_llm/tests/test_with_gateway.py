"""The stub behind the real LLM gateway (Vismay's GatewayLLMClient), over real HTTP: what demo #8 and the
load test rely on. Skipped where fssai-llm-gateway is not installed."""
from __future__ import annotations

import socket
import threading
import time

import pytest

gateway = pytest.importorskip("fssai_llm_gateway.client")

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from fssai_contracts.context import RunContext  # noqa: E402
from fssai_contracts.interfaces import ProviderUnavailable  # noqa: E402
from fssai_contracts.schemas import LLMMessage, PromptTemplate  # noqa: E402
from fssai_stub_llm.app import Settings, create_app  # noqa: E402


@pytest.fixture(scope="module")
def stub_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(Settings(latency_mean_s=0.05, latency_p95_s=0.1, seed=3))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def _client(url: str, **kw):
    env = {"LLM_BASE_URL": f"{url}/v1", "LLM_MODEL": "stub-model", "LLM_TIMEOUT_S": "5", "LLM_MAX_RETRIES": "1",
           "LLM_PRICE_PROMPT_PER_1K": "0.001", "LLM_PRICE_COMPLETION_PER_1K": "0.002",
           "BREAKER_FAILURE_THRESHOLD": "2", "BREAKER_COOLDOWN_S": "60", **kw}
    client = gateway.GatewayLLMClient.from_env(env)
    client.sleep = lambda s: None  # no real backoff waits in tests
    return client


def _set_faults(url: str, **faults) -> None:
    httpx.post(f"{url}/admin/faults", json=faults).raise_for_status()


def test_gateway_gets_tokens_and_cost_from_the_stub(stub_url):
    _set_faults(stub_url, down="0")
    ctx = RunContext.new()
    prompt = PromptTemplate(name="classifier", version="v1", system="[prompt:classifier@v1] s", user_template="{x}")
    resp = _client(stub_url).complete(prompt.render(x="label"), ctx, agent="classifier", step="classify",
                                      prompt=prompt)
    assert resp.text == "stub response" and resp.prompt_tokens > 0 and resp.completion_tokens > 0
    assert resp.cost_usd > 0
    (step,) = [s for s in ctx.steps if s.kind == "llm"]
    assert step.prompt_name == "classifier" and step.prompt_version == "v1" and step.error is None


def test_stub_down_opens_the_breaker(stub_url):
    _set_faults(stub_url, down="1")
    client = _client(stub_url)
    messages = [LLMMessage(role="system", content="[prompt:x@1] s"), LLMMessage(role="user", content="u")]
    try:
        for _ in range(2):  # threshold 2: two failed calls open it
            with pytest.raises(ProviderUnavailable):
                client.complete(messages, RunContext.new(), agent="a", step="s")
        t0 = time.perf_counter()
        with pytest.raises(ProviderUnavailable, match="(?i)open"):
            client.complete(messages, RunContext.new(), agent="a", step="s")
        assert time.perf_counter() - t0 < 0.5  # fails fast: no HTTP call while open
    finally:
        _set_faults(stub_url, down="0")
