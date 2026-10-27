"""Run every Python package's tests, each in its own pytest process (make test; CI does the same).

    python tools/scripts/test_all.py              # with the interpreter you call it with (use the .venv's)
    python tools/scripts/test_all.py packages/gate    # only the packages named

One process per package keeps same-named test files in different packages from clashing. A package
whose dependencies aren't installed in this environment is reported as skipped, not failed: install it
with `pip install -e "<path>[test]"` (setup_dev.py installs your own). Exit 1 if any package fails.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ["packages/contracts", "tools/scripts", "packages/observability", "packages/retrieval", "packages/ingest", "packages/llm_gateway",
            "packages/run_store", "packages/prompts", "packages/guardrails", "packages/agents", "packages/gate", "packages/verification",
            "packages/eval", "apps/stub_llm", "apps/worker", "apps/api"]


def main(argv: list[str]) -> int:
    chosen = argv or PACKAGES
    unknown = [p for p in chosen if not (ROOT / p).is_dir()]
    if unknown:
        print(f"no such package folder: {', '.join(unknown)}")
        return 2
    results: dict[str, str] = {}
    for package in chosen:
        if not any((ROOT / package).rglob("test_*.py")):
            results[package] = "no tests"
            continue
        proc = subprocess.run([sys.executable, "-m", "pytest", package, "-q", "-p", "no:cacheprovider"],
                              cwd=ROOT, capture_output=True, text=True)
        summary = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
        if proc.returncode == 0:
            results[package] = f"ok      {summary}"
        elif "ModuleNotFoundError" in proc.stdout + proc.stderr and proc.returncode in (1, 2, 4):
            missing = next((line.strip() for line in (proc.stdout + proc.stderr).splitlines()
                            if "ModuleNotFoundError" in line), "")
            results[package] = f"skipped not installed here ({missing.split(':')[-1].strip()})"
        else:
            results[package] = f"FAILED  {summary}"
            print(proc.stdout[-4000:], proc.stderr[-2000:], sep="\n")
    width = max(len(p) for p in results)
    for package, outcome in results.items():
        print(f"{package:<{width}}  {outcome}")
    return 1 if any(v.startswith("FAILED") for v in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
