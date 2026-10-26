"""Per-client rate limiting (D7): a token bucket per X-Client-Id.

RATE_LIMIT_BURST tokens per client, refilled at RATE_LIMIT_PER_MIN per minute; each submission takes one.
RedisTokenBucket is shared by every API replica (one Lua script, so take-and-refill is atomic across them);
MemoryTokenBucket is per process, for local runs and tests. RATE_LIMIT_PER_MIN=0 turns limiting off.

If Redis is unreachable the limiter fails open: the request is let through and the failure is logged and
counted. Shutting every client out because a counter store is down would be the worse failure, and the API's
own queue (same Redis) answers 503 in that case anyway.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Protocol

from prometheus_client import Counter

log = logging.getLogger("fssai.gate")
LIMITER_UNAVAILABLE = Counter("fssai_gate_rate_limit_unavailable_total",
                              "Rate-limit checks let through because Redis was unreachable (fail open)")

# KEYS[1] bucket key; ARGV[1] refill per second; ARGV[2] burst. Uses the Redis server clock, so API replicas with
# skewed clocks still agree. Floats come back as strings (Redis truncates Lua numbers to integers).
_TAKE = """
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1]) or burst
local ts = tonumber(state[2]) or now
tokens = math.min(burst, tokens + math.max(0, now - ts) * rate)
local allowed = 0
local retry = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry = (1 - tokens) / rate
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', KEYS[1], math.ceil(burst / rate) + 60)
return {allowed, tostring(retry)}
"""


class RateLimiter(Protocol):
    def take(self, client_id: str) -> tuple[bool, float]:
        """(allowed, retry_after_s)."""
        ...


class NoLimit:
    def take(self, client_id: str) -> tuple[bool, float]:
        return True, 0.0


class MemoryTokenBucket:
    def __init__(self, per_min: float, burst: int, clock=time.monotonic) -> None:
        self.rate, self.burst, self.clock = per_min / 60.0, max(1, burst), clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, client_id: str) -> tuple[bool, float]:
        with self._lock:
            now = self.clock()
            tokens, ts = self._buckets.get(client_id, (float(self.burst), now))
            tokens = min(self.burst, tokens + max(0.0, now - ts) * self.rate)
            if tokens >= 1:
                self._buckets[client_id] = (tokens - 1, now)
                return True, 0.0
            self._buckets[client_id] = (tokens, now)
            return False, (1 - tokens) / self.rate


class RedisTokenBucket:
    def __init__(self, redis_client, per_min: float, burst: int, prefix: str = "fssai:ratelimit:") -> None:
        self.redis, self.rate, self.burst, self.prefix = redis_client, per_min / 60.0, max(1, burst), prefix
        self._script = redis_client.register_script(_TAKE)
        self.failures = 0

    def take(self, client_id: str) -> tuple[bool, float]:
        try:
            allowed, retry = self._script(keys=[self.prefix + client_id], args=[self.rate, self.burst])
        except Exception as exc:  # noqa: BLE001 - fail open, see module docstring
            self.failures += 1
            LIMITER_UNAVAILABLE.inc()
            log.warning("rate limiter unavailable, letting the request through: %s: %s", type(exc).__name__, exc)
            return True, 0.0
        retry_s = float(retry)
        return bool(int(allowed)), (math.ceil(retry_s * 10) / 10 if retry_s > 0 else 0.0)
