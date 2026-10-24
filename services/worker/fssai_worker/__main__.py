"""`python -m fssai_worker`: consume the run queue (RUN_DISPATCH=queue). Scale with `--scale worker=N`.

SimpleWorker runs each job in this process instead of forking per job, so the pipeline is built
once, metrics accumulate on this process's /metrics port, and nothing per-run outlives the job.
"""
from __future__ import annotations

import logging
import os

import redis
from prometheus_client import start_http_server
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty, UnixSignalDeathPenalty

from .dispatch import QUEUE_NAME
from .jobs import default_deps


class Worker(SimpleWorker):
    # SIGALRM-based job timeouts don't exist on Windows; a timer thread does the same job there.
    death_penalty_class = UnixSignalDeathPenalty if os.name == "posix" else TimerDeathPenalty


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(message)s")
    start_http_server(int(os.environ.get("WORKER_METRICS_PORT", "9100") or 9100))
    default_deps()  # fail at start, not on the first job, if an IMPL_* path is wrong
    conn = redis.Redis.from_url(os.environ["REDIS_URL"])
    Worker([Queue(QUEUE_NAME, connection=conn)], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
