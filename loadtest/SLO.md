# Service level objective (D6)

Owner: Nishkal · Declared 2026-10-25, **before any load test was run**. The commit that adds this file is
the evidence that the target came first (spec D6: "a target set after seeing the results does not
satisfy this requirement"). Do not edit the targets below after measuring; add a dated amendment at the
end instead, with its reason.

## The objective

> **p95 of complete-run latency ≤ 60 s while 5 runs are in flight**, measured with the LLM replaced by
> the stub (mean 1.5 s, p95 4 s per call), on one worker replica; and **≤ 1 % of runs end in a system
> failure**.

| | Value |
|---|---|
| SLI | complete-run latency: submission to terminal status, measured by the client |
| Target | p95 ≤ **60 s** |
| Load | **5** concurrent runs (closed loop: 5 users, each submits, polls to the end, submits again) |
| Error budget | ≤ **1 %** of runs `failed`, or never reaching a terminal state within 180 s |
| Window | each load step runs 5 minutes after a 30 s warm-up; the step's p95 over that window is compared |
| Secondary | `POST /v1/runs` p95 ≤ 500 ms at the same load (the API must answer at once; A4) |

## Why these numbers (against spec §1)

The user is a regulatory affairs analyst checking a label **before it goes to print**. The alternative is
an analyst reading two regulations by hand, which takes tens of minutes per label, and a mistake costs a
print rerun or a recall. The check is part of a desk workflow, not a checkout page. Nobody waits on it
in real time, but an analyst does wait at the screen for it, so it should finish while they are still
looking at the label.

- **60 s.** The agent makes several model calls per run: a classifier call, several researcher turns, a
  verifier call, and a second research attempt when verification fails. That is about 6–10 calls at the
  stub's 1.5 s mean, or 9–15 s typical, with a tail when calls hit the 4 s p95 or a retry happens. The
  run has a hard wall-clock bound of 90 s (`RUN_MAX_WALL_S`), after which it is escalated incomplete.
  60 s at p95 leaves room for queue wait and the tail while staying clear of that bound. A minute is
  short against a manual check of tens of minutes, and long enough not to force a design that skips
  the verify-and-retry loop the spec requires (§5).
- **5 concurrent.** A team of 10–20 analysts submitting labels during a working day rarely has more
  than a handful of checks in flight at once. Five is a realistic busy moment for one deployment. The
  load test steps beyond it (10, 20) to find where the target breaks, as D6 asks.
- **One worker replica.** The target is for the default deployment. `--scale worker=3` is measured
  separately (A7) to see whether scaling moves the failure point.
- **1 % system failures.** Escalations (`regulatory-review`, including `complete=false` with an honest
  reason) are correct answers, not failures. A failure is a run that crashed (`failed`) or never
  finished. One in a hundred is the most an analyst should have to resubmit.

## How it is measured

- **Tool:** Locust (`loadtest/locustfile.py`). Each simulated user `POST`s a valid label check to
  `/v1/runs` with its own `X-Client-Id`, then polls `GET /v1/runs/{id}` every 0.5 s until the state is
  `completed` or `failed`. The time from just before the `POST` to the poll that sees the terminal state
  is reported as a custom Locust request named `full_run`. Polling adds at most 0.5 s.
- **LLM:** the stub service (`services/stub_llm`), `STUB_LATENCY_MEAN_S=1.5`, `STUB_LATENCY_P95_S=4`,
  log-normal, so the test measures our system and not a free tier's rate limits.
- **Steps:** 1, 2, 5, 10, 20 concurrent users, 5 minutes each (`loadtest/run_matrix.py`), first with
  one worker, then with `--scale worker=3`, with the cache on and off (D7).
- **Recorded per run:** OS, CPU, Docker memory limit, git commit, index version and stub settings, so
  results from different laptops are not compared as if they were the same machine.
- **Pass/fail:** the 5-user step's `full_run` p95 ≤ 60 s with failures ≤ 1 %. The **failure
  concurrency** is the lowest step whose p95 exceeds 60 s. The component responsible is named from the
  traces and the dashboard (queue wait vs. worker time vs. retrieval vs. stub latency).

## Monitoring the same objective live

`observability/prometheus/rules/slo.yml` turns this into burn-rate alerts on the worker's
`fssai_run_duration_seconds` histogram. That histogram covers execution time only; the client-side
`full_run` above also includes queue wait. Bad events are runs slower than 60 s (budget 5 %, since p95)
and failed runs (budget 1 %). Alerts fire on a fast burn (5 m and 1 h windows, 14.4×) and a slow
burn (30 m and 6 h windows, 6×).
