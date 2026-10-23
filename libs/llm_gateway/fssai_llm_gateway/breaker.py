"""Circuit breaker (A5): after N consecutive failed calls the provider is skipped for a cooldown,
then one trial call is let through (half-open). Success closes it; failure opens it again.

The state lives in a store so that every scaled worker sees the same breaker (A7): Redis in
Compose, process memory for local development and tests.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Literal, Protocol

from fssai_contracts.interfaces import ProviderUnavailable

from .metrics import BREAKER_OPENED, BREAKER_STATE

State = Literal["closed", "open", "half_open"]
_GAUGE = {"closed": 0, "half_open": 1, "open": 2}


class BreakerOpen(ProviderUnavailable):
    """The breaker is open (or another caller holds the half-open trial): failing fast."""


class BreakerStore(Protocol):
    def opened_at(self, name: str) -> float | None: ...
    def record_failure(self, name: str) -> int: ...
    def open(self, name: str, now: float) -> None: ...
    def reset(self, name: str) -> None: ...
    def try_acquire_trial(self, name: str, ttl_s: float) -> bool: ...


class MemoryBreakerStore:
    """shortcut: per-process state, so each worker trips on its own; use RedisBreakerStore when scaled."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._opened: dict[str, float] = {}
        self._trial_until: dict[str, float] = {}

    def opened_at(self, name):
        return self._opened.get(name)

    def record_failure(self, name):
        with self._lock:
            self._failures[name] = self._failures.get(name, 0) + 1
            return self._failures[name]

    def open(self, name, now):
        with self._lock:
            self._opened[name] = now
            self._trial_until.pop(name, None)

    def reset(self, name):
        with self._lock:
            self._failures.pop(name, None)
            self._opened.pop(name, None)
            self._trial_until.pop(name, None)

    def try_acquire_trial(self, name, ttl_s):
        with self._lock:
            now = time.monotonic()
            if self._trial_until.get(name, 0) > now:
                return False
            self._trial_until[name] = now + ttl_s
            return True


class RedisBreakerStore:
    """Shared by every process. Keys: fssai:breaker:<name> (hash) and fssai:breaker:<name>:trial."""

    def __init__(self, redis) -> None:
        self.redis = redis

    @classmethod
    def from_url(cls, url: str) -> RedisBreakerStore:
        import redis
        return cls(redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2))

    def _key(self, name: str) -> str:
        return f"fssai:breaker:{name}"

    def opened_at(self, name):
        raw = self.redis.hget(self._key(name), "opened_at")
        return float(raw) if raw is not None else None

    def record_failure(self, name):
        return int(self.redis.hincrby(self._key(name), "failures", 1))

    def open(self, name, now):
        pipe = self.redis.pipeline()
        pipe.hset(self._key(name), "opened_at", now)
        pipe.delete(f"{self._key(name)}:trial")
        pipe.execute()

    def reset(self, name):
        self.redis.delete(self._key(name), f"{self._key(name)}:trial")

    def try_acquire_trial(self, name, ttl_s):
        return bool(self.redis.set(f"{self._key(name)}:trial", "1", nx=True, px=max(1, int(ttl_s * 1000))))


class CircuitBreaker:
    def __init__(self, name: str, store: BreakerStore, *, threshold: int = 5, cooldown_s: float = 30.0,
                 clock: Callable[[], float] = time.time) -> None:
        self.name, self.store, self.threshold, self.cooldown_s, self.clock = name, store, threshold, cooldown_s, clock

    def state(self) -> State:
        opened = self.store.opened_at(self.name)
        if opened is None:
            state: State = "closed"
        elif self.clock() - opened < self.cooldown_s:
            state = "open"
        else:
            state = "half_open"
        BREAKER_STATE.labels(provider=self.name).set(_GAUGE[state])
        return state

    def before_call(self) -> State:
        """Returns the state the call runs under; raises BreakerOpen to fail fast."""
        state = self.state()
        if state == "open":
            raise BreakerOpen(f"circuit open for provider '{self.name}'")
        if state == "half_open" and not self.store.try_acquire_trial(self.name, self.cooldown_s):
            raise BreakerOpen(f"circuit half-open for provider '{self.name}', trial call in progress")
        return state

    def on_success(self) -> None:
        self.store.reset(self.name)
        BREAKER_STATE.labels(provider=self.name).set(0)

    def on_failure(self, state: State) -> None:
        failures = self.store.record_failure(self.name)
        if state == "half_open" or failures >= self.threshold:
            self.store.open(self.name, self.clock())
            BREAKER_OPENED.labels(provider=self.name).inc()
            BREAKER_STATE.labels(provider=self.name).set(2)
