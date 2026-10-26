"""Demo #1 rehearsal: a fresh clone, `cp .env.example .env`, one `docker compose up`, then the smoke test.

    python tools/scripts/clean_clone_test.py                 # clones this repo's committed HEAD
    python tools/scripts/clean_clone_test.py --remote        # clones GitHub main, exactly what an examiner gets
    python tools/scripts/clean_clone_test.py --env-extra my-provider.env   # also append these lines to .env

Runs under its own Compose project name and host ports, so it never touches a stack you already have
running, and always removes its containers and volumes at the end (--keep to leave them for debugging).
Run it before every demo rehearsal (S4.1). Exit 0 = a stranger's clean clone boots and serves a request.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOTE = "https://github.com/VismayHS/FSSAI_Label_Compliance_Agent.git"
PROJECT = "fssai-cleanclone"
PORTS = {"API_HOST_PORT": 18000, "WEB_HOST_PORT": 18080, "GRAFANA_HOST_PORT": 13000,
         "PROMETHEUS_HOST_PORT": 19090, "JAEGER_UI_HOST_PORT": 26686, "STUB_LLM_HOST_PORT": 18081}


def sh(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("  $", " ".join(args))
    return subprocess.run(args, cwd=cwd, check=check)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--remote", action="store_true", help=f"clone {REMOTE} (branch main) instead of local HEAD")
    p.add_argument("--branch", default="main", help="branch to clone with --remote")
    p.add_argument("--env-extra", type=Path, help="file whose lines are appended to the fresh .env (e.g. a key)")
    p.add_argument("--timeout", type=float, default=900, help="seconds for build + start + smoke")
    p.add_argument("--keep", action="store_true", help="leave the stack and folder for debugging")
    args = p.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the subprocesses' output

    work = Path(tempfile.mkdtemp(prefix="fssai-clean-"))
    clone = work / "repo"
    t0 = time.monotonic()
    ok = False
    try:
        print(f"1. clone into {clone}")
        if args.remote:
            sh("git", "clone", "--depth", "1", "--branch", args.branch, REMOTE, str(clone), cwd=work)
        else:
            sh("git", "clone", "--no-local", str(ROOT), str(clone), cwd=work)  # committed HEAD only, no local files

        print("2. cp .env.example .env  (plus test-only host ports so nothing clashes)")
        env = (clone / ".env.example").read_text(encoding="utf-8")
        env += "\n# clean_clone_test.py: separate host ports\n" + "".join(f"{k}={v}\n" for k, v in PORTS.items())
        if args.env_extra:
            env += "\n" + args.env_extra.read_text(encoding="utf-8")
        (clone / ".env").write_text(env, encoding="utf-8", newline="\n")

        print("3. docker compose up -d --build")
        up = sh("docker", "compose", "-p", PROJECT, "up", "-d", "--build", cwd=clone, check=False)
        if up.returncode != 0:
            print("  FAIL docker compose up exited non-zero")
            return 1

        print("4. smoke test")
        remaining = max(60.0, args.timeout - (time.monotonic() - t0))
        smoke = sh(sys.executable, str(clone / "tools" / "scripts" / "smoke.py"), "--base-url",
                   f"http://localhost:{PORTS['API_HOST_PORT']}", "--timeout", str(int(remaining)), cwd=clone, check=False)
        ok = smoke.returncode == 0
        if not ok:
            sh("docker", "compose", "-p", PROJECT, "ps", "-a", cwd=clone, check=False)
            sh("docker", "compose", "-p", PROJECT, "logs", "--tail=40", "api", "worker", cwd=clone, check=False)
    finally:
        if args.keep:
            print(f"kept: {clone} (docker compose -p {PROJECT} down -v to remove)")
        else:
            if clone.exists():
                sh("docker", "compose", "-p", PROJECT, "down", "-v", "--remove-orphans", cwd=clone, check=False)
            shutil.rmtree(work, ignore_errors=True)
    minutes = (time.monotonic() - t0) / 60
    print(f"clean-clone test {'PASSED' if ok else 'FAILED'} in {minutes:.1f} min")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
