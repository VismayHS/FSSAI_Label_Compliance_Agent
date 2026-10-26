"""python -m fssai_eval <command> (contexts/Vihaan.md V3.2-V3.4 and extras). See eval/README.md.

    run         --scenarios eval/scenarios.jsonl --tag <name> [--judge reference|llm|trulens] [--only id,...]
    compare     <tagA> <tagB>                     before/after table with deltas (V3.3)
    gate        --baseline <tag> --candidate <tag> exit 1 if the candidate regressed (CI regression gate)
    live        --sample 10 [--every 300]          score recent runs into quality_scores (L6)
    candidates  [--days 7] [--feedback-file f]     unsatisfactory feedback -> draft scenarios (eval/candidates.jsonl)
    calibrate   template|score                     LLM-judge agreement with hand labels (Cohen's kappa)

The `run` options are the agreed interface (Namith's prompt comparison and Nishkal's chunking change call it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_env_file(path: Path) -> int:
    """KEY=VALUE lines of a .env file into os.environ, without overriding what the shell already set (so CI and
    Compose win). Inline "  # comment" text is dropped, as in .env.example. Returns how many were set."""
    import os
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value
            n += 1
    return n


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fssai_eval", description="Run and score the eval set (L3, L6).")
    p.add_argument("--env-file", default=".env", help="load settings from this file first ('' to skip)")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run every scenario through the configured pipeline")
    run.add_argument("--scenarios", default="eval/scenarios.jsonl", help="EvalScenario JSON lines")
    run.add_argument("--tag", required=True, help="results go to eval/results/<tag>.json")
    run.add_argument("--judge", default=None, help="reference (offline, default) | llm | trulens; or EVAL_JUDGE")
    run.add_argument("--only", default="", help="comma-separated scenario ids")
    run.add_argument("--out-dir", default="eval/results")
    run.add_argument("--quiet", action="store_true")

    cmp_ = sub.add_parser("compare", help="before/after table of two results")
    cmp_.add_argument("before")
    cmp_.add_argument("after")
    cmp_.add_argument("--out-dir", default="eval/results")

    gate = sub.add_parser("gate", help="fail (exit 1) if a candidate result regressed against a baseline")
    gate.add_argument("--baseline", required=True)
    gate.add_argument("--candidate", required=True)
    gate.add_argument("--max-hallucination-increase", type=float, default=0.0)
    gate.add_argument("--max-route-accuracy-drop", type=float, default=0.05)
    gate.add_argument("--out-dir", default="eval/results")

    live = sub.add_parser("live", help="score a sample of recent runs into quality_scores")
    live.add_argument("--sample", type=int, default=None, help="runs per round (default LIVE_SCORE_SAMPLE or 10)")
    live.add_argument("--judge", default=None)
    live.add_argument("--every", type=float, default=None, help="repeat every N seconds (the Compose service)")

    cand = sub.add_parser("candidates", help="unsatisfactory feedback -> draft eval scenarios")
    cand.add_argument("--days", type=int, default=7)
    cand.add_argument("--feedback-file", type=Path, default=None, help="JSON lines of feedback instead of Postgres")
    cand.add_argument("--scenarios", default="eval/scenarios.jsonl")
    cand.add_argument("--out", type=Path, default=Path("eval/candidates.jsonl"))

    cal = sub.add_parser("calibrate", help="LLM-judge agreement with hand labels")
    cal.add_argument("action", choices=["template", "score"])
    cal.add_argument("--labels", type=Path, default=Path("eval/calibration/support-labels.jsonl"))
    cal.add_argument("--scenarios", default="eval/scenarios.jsonl")
    cal.add_argument("--limit", type=int, default=20)
    cal.add_argument("--judge", default="llm")
    return p


def _run(args) -> int:
    from .judges import make_judge
    from .runner import load_scenarios, run_eval, summary_table, write_results

    scenarios = load_scenarios(args.scenarios)
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    progress = None if args.quiet else (lambda line: print(line, file=sys.stderr))
    results = run_eval(scenarios, args.tag, judge=make_judge(args.judge), only=only, progress=progress)
    path = write_results(results, Path(args.out_dir))
    print(summary_table(results))
    print(f"\nwrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.env_file:
        load_env_file(Path(args.env_file))
    if args.command == "run":
        return _run(args)
    if args.command == "compare":
        from .runner import compare, load_results
        out = Path(args.out_dir)
        print(compare(load_results(args.before, out), load_results(args.after, out)))
        return 0
    if args.command == "gate":
        from .runner import load_results, regression_gate
        out = Path(args.out_dir)
        fails = regression_gate(load_results(args.baseline, out), load_results(args.candidate, out),
                                max_hallucination_increase=args.max_hallucination_increase,
                                max_route_accuracy_drop=args.max_route_accuracy_drop)
        for f in fails:
            print(f"REGRESSION: {f}", file=sys.stderr)
        print("eval gate: " + ("FAILED" if fails else "passed"))
        return 1 if fails else 0
    if args.command == "live":
        import os
        from .live import main as live_main
        sample = args.sample or int(os.environ.get("LIVE_SCORE_SAMPLE", "").split("#", 1)[0].strip() or 10)
        return live_main(sample, args.judge, args.every)
    if args.command == "candidates":
        from fssai_contracts.registry import build
        from .loop import candidates, feedback_rows
        from .runner import load_scenarios
        existing = {s.scenario_id for s in load_scenarios(args.scenarios)}
        if args.out.exists():
            existing |= {json.loads(x)["scenario_id"] for x in args.out.read_text(encoding="utf-8").splitlines() if x.strip()}
        new = candidates(feedback_rows(args.days, args.feedback_file), build("run_store"), existing)
        with args.out.open("a", encoding="utf-8") as f:
            for s in new:
                f.write(s.model_dump_json() + "\n")
        print(f"{len(new)} candidate scenario(s) appended to {args.out}; review each before moving it into the eval set")
        return 0
    if args.command == "calibrate":
        from .loop import calibration_score, calibration_template
        from .judges import make_judge
        from .runner import load_scenarios
        if args.action == "template":
            items = calibration_template(load_scenarios(args.scenarios), args.limit)
            args.labels.parent.mkdir(parents=True, exist_ok=True)
            args.labels.write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
            print(f"wrote {len(items)} items to {args.labels}: set each human_label to supported or unsupported")
            return 0
        items = [json.loads(x) for x in args.labels.read_text(encoding="utf-8").splitlines() if x.strip()]
        print(json.dumps(calibration_score(items, make_judge(args.judge)), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
