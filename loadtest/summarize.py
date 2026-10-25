"""Turn a run_matrix results folder into the table D6 asks for: RPS, p50, p95 against the SLO, met or not,
and the concurrency at which the target fails.

    python loadtest/summarize.py loadtest/results/<folder>

The targets below are copied from loadtest/SLO.md (declared before measuring); change them only there first.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

SLO_P95_S = 60.0          # complete-run p95 target
SLO_USERS = 5             # concurrency the target is declared at
ERROR_BUDGET = 0.01       # share of runs allowed to fail
SUBMIT_P95_S = 0.5        # secondary: POST /v1/runs p95


def _row(path: Path, name: str) -> dict | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        return next((r for r in csv.DictReader(fh) if r["Name"] == name), None)


def _num(row: dict | None, key: str) -> float:
    try:
        return float(row[key]) if row and row.get(key) not in (None, "", "N/A") else float("nan")
    except ValueError:
        return float("nan")


def steps(folder: Path) -> list[dict]:
    out = []
    for stats in sorted(folder.glob("w*_u*_stats.csv")):
        m = re.match(r"w(\d+)_u(\d+)_stats\.csv", stats.name)
        scale, users = int(m.group(1)), int(m.group(2))
        run, submit = _row(stats, "full_run"), _row(stats, "POST /v1/runs")
        n, fails = _num(run, "Request Count"), _num(run, "Failure Count")
        outcomes_path = folder / f"w{scale}_u{users}_outcomes.json"
        out.append({
            "workers": scale, "users": users, "runs": int(n) if n == n else 0,
            "runs_per_s": _num(run, "Requests/s"), "p50_s": _num(run, "50%") / 1000, "p95_s": _num(run, "95%") / 1000,
            "max_s": _num(run, "Max Response Time") / 1000, "fail_ratio": (fails / n) if n else float("nan"),
            "submit_p95_s": _num(submit, "95%") / 1000,
            "outcomes": json.loads(outcomes_path.read_text()) if outcomes_path.exists() else {},
        })
    return sorted(out, key=lambda s: (s["workers"], s["users"]))


def met(step: dict) -> bool:
    return step["p95_s"] <= SLO_P95_S and step["fail_ratio"] <= ERROR_BUDGET


def summarize(folder: Path) -> str:
    folder = Path(folder)
    rows = steps(folder)
    meta = json.loads((folder / "meta.json").read_text()) if (folder / "meta.json").exists() else {}
    lines = [f"SLO: full_run p95 <= {SLO_P95_S:g} s at {SLO_USERS} concurrent, failures <= {ERROR_BUDGET:.0%} "
             f"(loadtest/SLO.md)", f"machine: {json.dumps(meta.get('machine', {}))}", "",
             "| workers | users | runs | runs/s | p50 (s) | p95 (s) | max (s) | failed | submit p95 (s) | SLO |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s in rows:
        verdict = "met" if met(s) else "**missed**"
        lines.append(f"| {s['workers']} | {s['users']} | {s['runs']} | {s['runs_per_s']:.2f} | {s['p50_s']:.1f} | "
                     f"{s['p95_s']:.1f} | {s['max_s']:.1f} | {s['fail_ratio']:.1%} | {s['submit_p95_s']:.3f} | {verdict} |")
    lines.append("")
    for scale in sorted({s["workers"] for s in rows}):
        mine = [s for s in rows if s["workers"] == scale]
        target = next((s for s in mine if s["users"] == SLO_USERS), None)
        breaking = next((s["users"] for s in mine if not met(s)), None)
        lines.append(f"- workers={scale}: target step ({SLO_USERS} users) "
                     f"{'not measured' if target is None else ('MET' if met(target) else 'MISSED')}; "
                     f"SLO first fails at {breaking if breaking else '> ' + str(max(s['users'] for s in mine))} users")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python loadtest/summarize.py loadtest/results/<folder>")
    print(summarize(Path(sys.argv[1])))
