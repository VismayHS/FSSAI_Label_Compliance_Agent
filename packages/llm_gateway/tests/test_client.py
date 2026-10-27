"""GatewayLLMClient behaviour (Vismay.md S2.1). No network: httpx is mocked with respx."""
from __future__ import annotations

import json

import fakeredis
import httpx
import pytest
import respx

from fssai_contracts.context import BudgetExceeded, RunContext, RunLimits
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import LLMMessage, PromptTemplate
from fssai_llm_gateway.breaker import MemoryBreakerStore, RedisBreakerStore
from fssai_llm_gateway.client import GatewayLLMClient, Provider

PRIMARY = Provider("primary", "https://primary.test/v1", "key-1", "model-a", 0.5, 1.5)
FALLBACK = Provider("fallback", "https://fallback.test/v1", "", "model-b")
MSGS = [LLMMessage(role="system", content="[prompt:classifier@v1] be brief"), LLMMessage(role="user", content="hi")]
PROMPT = PromptTemplate(name="classifier", version="v1", system="s", user_template="{x}")


def ok(text="answer", pt=1000, ct=200):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}],
                                     "usage": {"prompt_tokens": pt, "completion_tokens": ct}})


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def make(fallback=None, *, store=None, clock=None, retries=2, sleeps=None, threshold=3, cooldown=30.0):
    sleeps = sleeps if sleeps is not None else []
    return GatewayLLMClient(PRIMARY, fallback, max_retries=retries, breaker_store=store or MemoryBreakerStore(),
                            breaker_threshold=threshold, breaker_cooldown_s=cooldown,
                            sleep=sleeps.append, jitter=lambda: 1.0, clock=clock or Clock())


def ctx(**limits):
    return RunContext.new("run-1", limits=RunLimits(**limits) if limits else RunLimits())


def call(client, c=None, **kw):
    return client.complete(MSGS, c or ctx(), agent="classifier", step="classify", prompt=PROMPT, **kw)


@respx.mock
def test_success_records_one_llm_step_with_tokens_cost_and_prompt_version():
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=ok())
    c = ctx()
    resp = call(make(), c, json_mode=True)

    assert resp.text == "answer" and resp.model_alias == "primary" and not resp.degraded
    assert resp.cost_usd == pytest.approx(1000 * 0.5 / 1000 + 200 * 1.5 / 1000)
    sent = json.loads(route.calls.last.request.content)
    assert sent["response_format"] == {"type": "json_object"} and sent["model"] == "model-a"
    assert sent["messages"][0]["content"].startswith("[prompt:classifier@v1]")
    assert route.calls.last.request.headers["authorization"] == "Bearer key-1"
    # Cloudflare-fronted providers (Groq) refuse library default User-Agents with 403 (docs/contexts/Namith.md M0.2)
    assert route.calls.last.request.headers["user-agent"].startswith("fssai-label-agent/")
    [step] = c.steps
    assert (step.kind, step.agent, step.name) == ("llm", "classifier", "classify")
    assert (step.prompt_name, step.prompt_version) == ("classifier", "v1")
    assert (step.prompt_tokens, step.completion_tokens) == (1000, 200)
    assert step.output["attempts"] == 1 and step.error is None
    assert "model-a" not in step.model_dump_json()  # traces carry the alias, never the model id (D4)
    assert c.prompt_versions == {"classifier": "v1"}


@respx.mock
def test_retryable_errors_are_retried_with_backoff_then_succeed():
    route = respx.post("https://primary.test/v1/chat/completions").mock(
        side_effect=[httpx.Response(503), httpx.ConnectError("boom"), ok()])
    sleeps: list[float] = []
    c = ctx()
    resp = call(make(sleeps=sleeps), c)
    assert resp.text == "answer"
    assert route.call_count == 3
    assert sleeps == [0.5, 1.0]  # full jitter (jitter=1.0 here) on base 0.5 s, doubling
    assert c.steps[-1].output["attempts"] == 3 and len([s for s in c.steps if s.kind == "llm"]) == 1


@respx.mock
def test_retry_after_header_is_honoured():
    respx.post("https://primary.test/v1/chat/completions").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "4"}), ok()])
    sleeps: list[float] = []
    call(make(sleeps=sleeps))
    assert sleeps == [4.0]


@respx.mock
def test_retries_exhausted_raises_provider_unavailable_and_records_the_error():
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(500))
    c = ctx()
    with pytest.raises(ProviderUnavailable, match="HTTP 500 after 3 attempt"):
        call(make(retries=2), c)
    assert route.call_count == 3
    [step] = c.steps
    assert step.error and "primary: HTTP 500" in step.error and step.cost_usd == 0


@respx.mock
def test_non_retryable_status_is_not_retried():
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(401))
    with pytest.raises(ProviderUnavailable, match="HTTP 401"):
        call(make())
    assert route.call_count == 1


@respx.mock
def test_malformed_reply_is_retried():
    route = respx.post("https://primary.test/v1/chat/completions").mock(
        side_effect=[httpx.Response(200, json={"oops": True}), ok()])
    assert call(make()).text == "answer" and route.call_count == 2


@respx.mock
def test_breaker_opens_after_threshold_and_fails_fast_without_http_calls():
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(500))
    client = make(retries=0, threshold=3)
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            call(client)
    assert route.call_count == 3
    with pytest.raises(ProviderUnavailable, match="circuit open"):
        call(client)
    assert route.call_count == 3  # no HTTP call while open


@respx.mock
def test_half_open_trial_success_closes_the_breaker():
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(500))
    clock = Clock()
    client = make(retries=0, threshold=1, cooldown=30, clock=clock)
    with pytest.raises(ProviderUnavailable):
        call(client)
    assert client.breakers["primary"].state() == "open"
    clock.now += 31
    assert client.breakers["primary"].state() == "half_open"
    route.mock(return_value=ok())
    assert call(client).text == "answer"
    assert client.breakers["primary"].state() == "closed"


@respx.mock
def test_half_open_trial_failure_reopens_the_breaker():
    respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(500))
    clock = Clock()
    client = make(retries=0, threshold=1, cooldown=30, clock=clock)
    with pytest.raises(ProviderUnavailable):
        call(client)
    clock.now += 31
    with pytest.raises(ProviderUnavailable):
        call(client)
    assert client.breakers["primary"].state() == "open"


@respx.mock
def test_fallback_is_used_when_primary_is_down_and_marked_degraded():
    respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(503))
    fb = respx.post("https://fallback.test/v1/chat/completions").mock(return_value=ok("from fallback"))
    c = ctx()
    resp = call(make(FALLBACK, retries=1), c)
    assert resp.degraded and resp.model_alias == "fallback" and resp.text == "from fallback"
    assert resp.cost_usd == 0.0
    assert "authorization" not in fb.calls.last.request.headers  # fallback has no key configured
    [step] = c.steps
    assert step.output["attempts"] == 3 and step.output["degraded"] is True


@respx.mock
def test_both_providers_down_raises_with_both_reasons():
    respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(503))
    respx.post("https://fallback.test/v1/chat/completions").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderUnavailable) as err:
        call(make(FALLBACK, retries=0))
    assert "primary: HTTP 503" in str(err.value) and "fallback: timeout" in str(err.value)


@respx.mock
def test_timeout_is_capped_by_the_run_deadline_and_no_retry_crosses_it(monkeypatch):
    # Freeze the run's clock: on a busy machine the real 0.5 s could pass before the first call (flaky).
    monkeypatch.setattr("fssai_contracts.context.time.monotonic", lambda: 1_000.0)
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(503))
    sleeps: list[float] = []
    c = ctx(max_wall_s=0.5)
    c.started = 1_000.0  # the field's default_factory captured the real clock
    with pytest.raises(ProviderUnavailable):
        call(make(retries=3, sleeps=sleeps), c)
    assert route.call_count == 1 and sleeps == []  # a 0.5 s backoff would cross the 0.5 s deadline
    assert route.calls.last.request.extensions["timeout"]["read"] <= 0.5


def test_expired_run_budget_raises_budget_exceeded_before_any_call():
    c = ctx(max_wall_s=0)
    with pytest.raises(BudgetExceeded):
        call(make(), c)


@respx.mock
def test_redis_breaker_state_is_shared_between_workers():
    respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(500))
    redis = fakeredis.FakeRedis()
    worker_a = make(retries=0, threshold=2, store=RedisBreakerStore(redis))
    worker_b = make(retries=0, threshold=2, store=RedisBreakerStore(redis))
    with pytest.raises(ProviderUnavailable):
        call(worker_a)
    with pytest.raises(ProviderUnavailable):
        call(worker_b)
    with pytest.raises(ProviderUnavailable, match="circuit open"):
        call(worker_a)  # opened by the two workers' failures together


def test_from_env_reads_config_and_requires_base_url_and_model():
    client = GatewayLLMClient.from_env({
        "LLM_BASE_URL": "https://p.test/v1/", "LLM_MODEL": "m", "LLM_MAX_RETRIES": "1",
        "LLM_PRICE_PROMPT_PER_1K": "0.2  # comment", "LLM_FALLBACK_BASE_URL": "https://f.test/v1",
        "LLM_FALLBACK_MODEL": "f", "BREAKER_FAILURE_THRESHOLD": "7"})
    assert [p.alias for p in client.providers] == ["primary", "fallback"]
    assert client.providers[0].base_url == "https://p.test/v1"
    assert client.providers[0].price_prompt_per_1k == 0.2 and client.max_retries == 1
    assert client.breakers["primary"].threshold == 7
    with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        GatewayLLMClient.from_env({"LLM_MODEL": "m"})
    with pytest.raises(RuntimeError, match="BREAKER_STORE"):
        GatewayLLMClient.from_env({"LLM_BASE_URL": "u", "LLM_MODEL": "m", "BREAKER_STORE": "disk"})


@respx.mock
def test_a_provider_json_validation_failure_is_retried_like_a_malformed_reply():
    # Groq answers 400 json_validate_failed when the model's own output was not valid JSON in JSON mode.
    bad = httpx.Response(400, json={"error": {"message": "Failed to generate JSON. Please adjust your prompt.",
                                              "type": "invalid_request_error", "code": "json_validate_failed",
                                              "failed_generation": "{not json"}})
    route = respx.post("https://primary.test/v1/chat/completions").mock(side_effect=[bad, ok('{"a": 1}')])
    c = ctx()
    assert call(make(), c, json_mode=True).text == '{"a": 1}'
    assert route.call_count == 2 and c.steps[-1].output["attempts"] == 2


@respx.mock
def test_other_client_errors_are_not_retried_and_name_only_the_providers_error_code():
    body = {"error": {"message": "The model `model-a` does not support this. Prompt was: secret label text",
                      "type": "invalid_request_error", "code": "model_not_supported"}}
    route = respx.post("https://primary.test/v1/chat/completions").mock(return_value=httpx.Response(400, json=body))
    c = ctx()
    with pytest.raises(ProviderUnavailable, match=r"HTTP 400 invalid_request_error/model_not_supported \(not retried\)"):
        call(make(), c)
    assert route.call_count == 1
    dumped = c.steps[-1].model_dump_json()
    assert "model-a" not in dumped and "secret label text" not in dumped  # the provider's message never reaches the trace


@respx.mock
@pytest.mark.parametrize("reset, wait", [("4.11s", 4.11), ("592ms", 0.592), ("1m2.5s", 62.5)])
def test_a_rate_limit_without_retry_after_waits_for_the_token_budget_to_refill(reset, wait):
    # Groq sends x-ratelimit-reset-tokens (time until the per-minute token budget refills) on a 429.
    limited = httpx.Response(429, headers={"x-ratelimit-reset-tokens": reset})
    respx.post("https://primary.test/v1/chat/completions").mock(side_effect=[limited, ok()])
    sleeps: list[float] = []
    c = ctx(max_wall_s=120)
    call(make(sleeps=sleeps), c)
    assert sleeps == [pytest.approx(wait)]


@respx.mock
def test_a_provider_tool_use_failure_is_retried_like_a_malformed_reply():
    # Some open models emit a tool call nobody offered; Groq answers 400 tool_use_failed. It is the model's output.
    bad = httpx.Response(400, json={"error": {"type": "invalid_request_error", "code": "tool_use_failed"}})
    route = respx.post("https://primary.test/v1/chat/completions").mock(side_effect=[bad, ok()])
    assert call(make()).text == "answer" and route.call_count == 2
