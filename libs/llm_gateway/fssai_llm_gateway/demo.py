"""Demo #8: the circuit breaker opens when the provider is down and recovers when it comes back (A5).

    docker compose exec worker python -m fssai_llm_gateway.demo        (or: make demo-breaker)

Drives the real GatewayLLMClient against Nishkal's stub LLM and switches the stub's faults at runtime:
  1. healthy call                                  -> breaker closed
  2. stub down: calls retry, then fail             -> breaker opens after BREAKER_FAILURE_THRESHOLD failures
  3. while open: calls fail fast, no HTTP at all   -> what the pipeline turns into regulatory-review, complete=false
  4. stub up, cooldown over: one trial call        -> half-open -> closed
Breaker state is in Redis when REDIS_URL is set (BREAKER_STORE=redis): while it is open, every worker replica's
next LLM call fails fast too, and their fssai_llm_breaker_state gauge reads 2. Exit 0 if all four held.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

from fssai_contracts.context import RunContext, RunLimits
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import LLMMessage

from .client import GatewayLLMClient

MESSAGES = [LLMMessage(role="system", content="[prompt:breaker-demo@v1] Reply with OK."),
            LLMMessage(role="user", content="ping")]


def set_faults(admin_url: str, down: str) -> None:
    req = urllib.request.Request(f"{admin_url}/admin/faults", data=json.dumps({"down": down}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def call(client: GatewayLLMClient) -> tuple[bool, float, str]:
    ctx = RunContext.new(limits=RunLimits(max_wall_s=60))
    t0 = time.monotonic()
    try:
        client.complete(MESSAGES, ctx, agent="demo", step="breaker_demo")
        return True, (time.monotonic() - t0) * 1000, "ok"
    except ProviderUnavailable as exc:
        return False, (time.monotonic() - t0) * 1000, str(exc)


def main() -> int:
    p = argparse.ArgumentParser(description="Circuit-breaker demo against the stub LLM (demo #8).")
    p.add_argument("--base-url", default="http://stub-llm:8080/v1", help="the stub's OpenAI-compatible URL")
    p.add_argument("--threshold", type=int, default=3, help="failures before the breaker opens")
    p.add_argument("--cooldown", type=float, default=8.0, help="seconds open before a trial call")
    args = p.parse_args()
    admin = args.base_url.rsplit("/v1", 1)[0]
    env = {**os.environ, "LLM_BASE_URL": args.base_url, "LLM_MODEL": "stub", "LLM_API_KEY": "",
           "LLM_MAX_RETRIES": "1", "LLM_TIMEOUT_S": "5", "LLM_FALLBACK_BASE_URL": "",
           "BREAKER_FAILURE_THRESHOLD": str(args.threshold), "BREAKER_COOLDOWN_S": str(args.cooldown),
           "BREAKER_STORE": "redis" if os.environ.get("REDIS_URL") else "memory"}
    client = GatewayLLMClient.from_env(env)
    breaker = client.breakers["primary"]
    breaker.store.reset("primary")  # a clean start, also for the replicas sharing this Redis key
    seen: dict[str, bool] = {}

    def show(label: str, ok: bool, ms: float, detail: str) -> None:
        print(f"  {label:<28} {'ok  ' if ok else 'FAIL'} {ms:7.0f} ms  breaker={breaker.state():<9} {detail[:70]}")

    try:
        print(f"1. provider healthy ({args.base_url}, breaker store: {env['BREAKER_STORE']})")
        set_faults(admin, "0")
        ok, ms, detail = call(client)
        show("call", ok, ms, detail)
        seen["healthy"] = ok and breaker.state() == "closed"

        print(f"2. provider down: each call retries once, then fails; opens after {args.threshold} failures")
        set_faults(admin, "1")
        for i in range(args.threshold):
            show(f"call {i + 1}", *call(client))
        seen["opened"] = breaker.state() == "open"

        print("3. breaker open: calls fail fast, no HTTP (the pipeline answers regulatory-review, complete=false)")
        fast = [call(client) for _ in range(3)]
        for i, r in enumerate(fast):
            show(f"call {args.threshold + i + 1}", *r)
        seen["fail_fast"] = all(not ok and "circuit open" in d and ms < 200 for ok, ms, d in fast)

        print(f"4. provider back; after the {args.cooldown:g}s cooldown one trial call closes the breaker")
        set_faults(admin, "0")
        time.sleep(args.cooldown + 0.5)
        show("trial call", *call(client))
        seen["recovered"] = breaker.state() == "closed"
    finally:
        try:
            set_faults(admin, "0")  # never leave the stub down
        except OSError:
            pass

    print("\n" + "\n".join(f"  {'ok  ' if v else 'FAIL'} {k}" for k, v in seen.items()))
    return 0 if all(seen.values()) and len(seen) == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
