"""python -m fssai_eval run --scenarios eval/scenarios.jsonl --tag <name> (contexts/Vihaan.md V3.2). Day-0 skeleton.

The options are the agreed interface (Namith's prompt comparison and Nishkal's chunking change call it);
the runner behind them is V3.2: every EvalScenario through build("pipeline") in-process, results to
eval/results/<tag>.json, the four L3 metrics computed as defined in your report section.
"""
from __future__ import annotations

import argparse
import sys


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fssai_eval", description="Run and score the eval set (L3).")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run every scenario through the configured pipeline")
    run.add_argument("--scenarios", default="eval/scenarios.jsonl", help="EvalScenario JSON lines")
    run.add_argument("--tag", required=True, help="results go to eval/results/<tag>.json")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    print(f"fssai_eval {args.command}: not built yet (contexts/Vihaan.md V3.2)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
