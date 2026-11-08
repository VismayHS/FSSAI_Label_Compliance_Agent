"""`python -m fssai_worker`: consume the run queue (RUN_DISPATCH=queue). Scale with `--scale worker=N`.

If a worker dies mid-run, another (or the restarted one) re-queues its job at the next maintenance pass, every
WORKER_MAINTENANCE_S (60 s); with PIPELINE_CHECKPOINTS=postgres the run continues at the node it had reached.

SimpleWorker runs each job in this process instead of forking per job, so the pipeline is built
once, metrics accumulate on this process's /metrics port, and nothing per-run outlives the job.
"""
from __future__ import annotations

import os

import redis
from fssai_observability import setup_logging, setup_tracing
from prometheus_client import start_http_server
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty, UnixSignalDeathPenalty

from .dispatch import QUEUE_NAME
from .jobs import default_deps


class Worker(SimpleWorker):
    # SIGALRM-based job timeouts don't exist on Windows; a timer thread does the same job there.
    death_penalty_class = UnixSignalDeathPenalty if os.name == "posix" else TimerDeathPenalty


def main() -> None:
    setup_logging("worker")
    setup_tracing("worker")
    start_http_server(int(os.environ.get("WORKER_METRICS_PORT", "9100") or 9100))
    default_deps()  # fail at start, not on the first job, if an IMPL_* path is wrong
    conn = redis.Redis.from_url(os.environ["REDIS_URL"])
    every = maintenance_interval()
    # RQ checks for maintenance only between blocking queue reads, and each read waits worker_ttl - 15 s (405 s by
    # default), so an idle worker would look for dead workers' jobs every ~7 min whatever the interval says.
    Worker([Queue(QUEUE_NAME, connection=conn)], connection=conn, maintenance_interval=every,
           worker_ttl=every + 15).work(with_scheduler=False)


def maintenance_interval() -> int:
    """How often this worker looks for jobs whose worker died (RQ's default is 10 min). A dead worker's job is
    abandoned once its started-registry entry expires (the job timeout + 60 s after it started), then re-queued
    once (dispatch.QueueDispatcher.submit). Measured on the stack: worker killed 2 s into a run, run resumed and
    completed 456 s later with RQ's 405 s queue-read wait; this interval removes most of that wait."""
    return int(os.environ.get("WORKER_MAINTENANCE_S", "").split("#", 1)[0].strip() or 60)


if __name__ == "__main__":
    main()
