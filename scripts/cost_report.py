"""L5 cost report from the run store: cost per 100 runs, cost by step and agent, the largest single driver.

    python scripts/cost_report.py                    # reads the Compose stack's Postgres (docker compose exec)
    python scripts/cost_report.py --out docs/report/cost.md --since 2026-11-01

Costs are recorded at call time by the LLM gateway (LLM_PRICE_*_PER_1K in .env) on every llm step and saved
per step in run_steps. Run a batch of real-provider runs first (e.g. Vihaan's eval set 4-5 times); runs on
the fakes or the stub cost $0 and the report says so. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUNS = """SELECT count(*), coalesce(sum(cost_usd), 0), coalesce(avg(cost_usd), 0),
                 coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY cost_usd), 0)
          FROM runs WHERE cost_usd IS NOT NULL AND updated_at >= '{since}'"""
BY = """SELECT {key}, count(*), sum(prompt_tokens), sum(completion_tokens), sum(s.cost_usd)
        FROM run_steps s JOIN runs r USING (run_id)
        WHERE r.cost_usd IS NOT NULL AND r.updated_at >= '{since}' AND s.kind = 'llm'
        GROUP BY {key} ORDER BY sum(s.cost_usd) DESC, count(*) DESC"""


def query(sql: str) -> list[list[str]]:
    out = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "sh", "-c",
                          'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --csv -v ON_ERROR_STOP=1'],
                         cwd=ROOT, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"query failed (is the stack up? docker compose ps):\n{out.stderr.strip()}")
    rows = list(csv.reader(io.StringIO(out.stdout)))
    return rows[1:]


def money(value: str | float) -> str:
    v = float(value)
    return f"${v:.6f}" if 0 < v < 0.01 else f"${v:.4f}"


def report(since: str) -> str:
    n, total, avg, p95 = query(RUNS.format(since=since))[0]
    n = int(n)
    lines = [f"# Cost report (L5)", "", f"Runs with a result since {since}: **{n}**", ""]
    if n == 0:
        return "\n".join(lines + ["No finished runs yet. Submit some, then run this again."])
    lines += ["| Metric | Value |", "|---|---|",
              f"| Total cost | {money(total)} |", f"| Mean cost per run | {money(avg)} |",
              f"| p95 cost per run | {money(p95)} |", f"| **Cost per 100 runs** | **{money(float(avg) * 100)}** |", ""]
    for key, title in (("s.name", "LLM step"), ("s.agent", "Agent")):
        rows = query(BY.format(key=key, since=since))
        lines += [f"## By {title.lower()}", "", f"| {title} | Calls | Prompt tokens | Completion tokens | Cost | Share |",
                  "|---|---|---|---|---|---|"]
        for name, calls, pt, ct, cost in rows:
            share = float(cost) / float(total) * 100 if float(total) else 0
            lines.append(f"| `{name}` | {calls} | {pt} | {ct} | {money(cost)} | {share:.0f}% |")
        if not rows:
            lines.append("| (no LLM calls recorded) | | | | | |")
        lines.append("")
    steps = query(BY.format(key="s.name", since=since))
    if float(total) == 0:
        lines.append("All recorded costs are $0: these runs used the fakes or the stub LLM, or LLM_PRICE_*_PER_1K is "
                     "unset. Set your provider's prices in .env and run real-provider runs.")
    elif steps:
        name, calls, pt, ct, cost = steps[0]
        lines.append(f"**Largest single cost driver:** the `{name}` step, {money(cost)} over {calls} calls "
                     f"({float(cost) / float(total) * 100:.0f}% of all spend, {int(pt) + int(ct)} tokens).")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--since", default="1970-01-01",
                   help="only runs updated on or after this date or UTC time (2026-11-01 or 2026-11-01T16:45)")
    p.add_argument("--out", type=Path, help="also write the report to this Markdown file")
    args = p.parse_args()
    try:
        # validated (it is placed into the SQL text): a date, or a UTC date and time
        since = (datetime.fromisoformat(args.since) if "T" in args.since else date.fromisoformat(args.since)).isoformat()
    except ValueError:
        p.error(f"--since must be a date like 2026-11-01 or a UTC time like 2026-11-01T16:45, not {args.since!r}")
    text = report(since)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
