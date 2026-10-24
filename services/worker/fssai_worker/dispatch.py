"""How a submitted run reaches execute_run (A4: a queue between submit and execute).

RUN_DISPATCH=queue   RQ queue on Redis (REDIS_URL). The API enqueues; `python -m fssai_worker` executes.
RUN_DISPATCH=inline  The API process runs it in a small thread pool. For local development without
                     Redis only; the API's /readyz says so. Default, so a fresh clone works with
                     nothing but `uvicorn`.
"""
from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Mapping, Protocol

from .jobs import Deps, execute_run

QUEUE_NAME = "fssai-runs"
JOB_FUNC = "fssai_worker.jobs.execute_run"


class Dispatcher(Protocol):
    mode: str

    def submit(self, payload: dict) -> Future | None: ...

    def ready(self) -> tuple[bool, str]: ...


class InlineDispatcher:
    """shortcut: runs inside the API process and dies with it; use RUN_DISPATCH=queue in Compose."""

    mode = "inline"

    def __init__(self, deps: Deps, workers: int = 2) -> None:
        self.deps = deps
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fssai-run")

    def submit(self, payload: dict) -> Future:
        return self.pool.submit(execute_run, payload, self.deps)

    def ready(self) -> tuple[bool, str]:
        return True, "inline execution (development mode, no queue)"


class QueueDispatcher:
    mode = "queue"

    def __init__(self, redis, *, job_timeout_s: int) -> None:
        from rq import Queue
        self.redis = redis
        self.queue = Queue(QUEUE_NAME, connection=redis)
        self.job_timeout_s = job_timeout_s

    def submit(self, payload: dict) -> None:
        self.queue.enqueue(JOB_FUNC, payload, job_id=payload["run_id"], job_timeout=self.job_timeout_s,
                           result_ttl=3600, failure_ttl=7 * 24 * 3600)
        return None

    def ready(self) -> tuple[bool, str]:
        try:
            self.redis.ping()
        except Exception as exc:  # noqa: BLE001 - any Redis error means not ready
            return False, f"queue unreachable: {type(exc).__name__}"
        return True, f"queue '{QUEUE_NAME}' reachable, {self.queue.count} job(s) waiting"


def from_env(env: Mapping[str, str], deps: Deps) -> Dispatcher:
    mode = env.get("RUN_DISPATCH", "inline").split("#", 1)[0].strip() or "inline"
    if mode == "inline":
        return InlineDispatcher(deps, workers=int(env.get("INLINE_WORKERS", "2") or 2))
    if mode == "queue":
        import redis
        conn = redis.Redis.from_url(env["REDIS_URL"], socket_timeout=5, socket_connect_timeout=5)
        wall_s = float(env.get("RUN_MAX_WALL_S", "90").split("#", 1)[0].strip() or 90)
        return QueueDispatcher(conn, job_timeout_s=int(wall_s) + 30)
    raise RuntimeError(f"RUN_DISPATCH must be 'inline' or 'queue', not '{mode}'")


def from_environ(deps: Deps) -> Dispatcher:
    return from_env(os.environ, deps)
