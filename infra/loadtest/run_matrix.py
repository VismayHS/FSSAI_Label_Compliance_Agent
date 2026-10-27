"""Run the load-test matrix of infra/loadtest/SLO.md and save the results (D6, A7, D7). Python, so it runs the
same on Windows and macOS.

    # whole stack under Compose with the stub LLM (LLM_BASE_URL=http://stub-llm:8080/v1 in .env)
    python infra/loadtest/run_matrix.py --host http://localhost:8000 --compose --scales 1 3
    # against whatever is already running (no scaling)
    python infra/loadtest/run_matrix.py --host http://localhost:8000 --users 1 2 5 --duration 60s

For every worker scale and every user count it runs a warm-up (discarded) and then the measured step,
writing Locust CSVs to infra/loadtest/results/<timestamp>-<label>/, plus meta.json describing the machine,
git commit, index and stub settings. Then it prints the summary table (infra/loadtest/summarize.py).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sh(*args: str, check: bool = True) -> str:
    out = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if check and out.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{out.stderr}")
    return out.stdout.strip()


def wait_ready(host: str, timeout_s: float = 300) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{host}/readyz", timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001 - not up yet
            pass
        time.sleep(3)
    raise SystemExit(f"{host}/readyz never became ready")


def machine_info() -> dict:
    info = {"os": f"{platform.system()} {platform.release()}", "machine": platform.machine(),
            "cpu": platform.processor() or platform.machine(), "cpu_count": os.cpu_count(),
            "python": platform.python_version()}
    docker = subprocess.run(["docker", "info", "--format", "{{.MemTotal}} {{.NCPU}} {{.ServerVersion}}"],
                            text=True, capture_output=True)
    if docker.returncode == 0 and docker.stdout.strip():
        mem, ncpu, version = docker.stdout.split()
        info["docker"] = {"memory_gb": round(int(mem) / 2**30, 1), "cpus": int(ncpu), "version": version}
    return info


def locust(host: str, users: int, duration: str, csv_prefix: Path | None, env: dict) -> None:
    args = [sys.executable, "-m", "locust", "-f", str(HERE / "locustfile.py"), "--headless", "--host", host,
            "-u", str(users), "-r", str(users), "--run-time", duration, "--only-summary", "--stop-timeout", "200"]
    if csv_prefix is not None:
        args += ["--csv", str(csv_prefix), "--csv-full-history"]
    subprocess.run(args, cwd=ROOT, env=env, check=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default="http://localhost:8000")
    p.add_argument("--users", type=int, nargs="+", default=[1, 2, 5, 10, 20])
    p.add_argument("--duration", default="5m")
    p.add_argument("--warmup", default="30s")
    p.add_argument("--compose", action="store_true", help="scale the worker with docker compose before each scale")
    p.add_argument("--scales", type=int, nargs="+", default=[1])
    p.add_argument("--label", default="", help="added to the results folder name, e.g. cache-off")
    p.add_argument("--out", default=str(HERE / "results"))
    args = p.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) / (stamp + (f"-{args.label}" if args.label else ""))
    out.mkdir(parents=True, exist_ok=True)
    meta = {"started_at": stamp, "host": args.host, "users": args.users, "duration": args.duration,
            "warmup": args.warmup, "scales": args.scales, "label": args.label,
            "git_commit": sh("git", "rev-parse", "--short", "HEAD", check=False),
            "machine": machine_info(),
            "settings": {k: os.environ.get(k) for k in ("STUB_LATENCY_MEAN_S", "STUB_LATENCY_P95_S", "CACHE_ENABLED",
                                                        "RETRIEVAL_MODE", "RATE_LIMIT_PER_MIN", "RUN_DISPATCH")}}
    try:
        with urllib.request.urlopen(f"{args.host}/readyz", timeout=5) as r:
            meta["readyz"] = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        meta["readyz"] = f"unreachable: {exc}"

    for scale in args.scales:
        if args.compose:
            print(f"== docker compose up -d --scale worker={scale}")
            sh("docker", "compose", "up", "-d", "--scale", f"worker={scale}")
            wait_ready(args.host)
        for users in args.users:
            env = {**os.environ, "LOADTEST_OUTCOMES": str(out / f"w{scale}_u{users}_outcomes.json")}
            print(f"== workers={scale} users={users}: warm-up {args.warmup}, then {args.duration}")
            locust(args.host, users, args.warmup, None, {**env, "LOADTEST_OUTCOMES": ""})
            locust(args.host, users, args.duration, out / f"w{scale}_u{users}", env)
    meta["finished_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    sys.path.insert(0, str(HERE))
    from summarize import summarize  # noqa: PLC0415 - sibling script

    print(summarize(out))
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
