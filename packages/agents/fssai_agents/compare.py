"""Compare two researcher prompt variants on the evaluation set (M3.2, L2; decision 205 names the tags).

    python -m fssai_agents.compare run                 # both variants, paced for a free tier, resumable
    python -m fssai_agents.compare run --only 1.1.0    # one variant (rerun after a rate limit; finished rows are kept)
    python -m fssai_agents.compare report              # print the table and the verdict
    python -m fssai_agents.compare report --write      # fill the report table and write the decision record

`run` shells out to `python -m fssai_eval run`, so it measures exactly what the runner measures, with the real LLM and
retriever that .env selects. The researcher and its draft prompt are pinned together (they are versioned in pairs), and
every other setting stays the same between the two runs. Needs the LLM key in .env; one run is about 12,500 tokens per
scenario, so use --pause-s to stay inside the provider's tokens-per-minute limit.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "packages" / "eval" / "results"
REPORT = ROOT / "docs" / "report" / "agent-design.md"
DECISION = ROOT / "docs" / "decisions" / "103-namith-prompt-comparison.md"
VARIANTS = ("1.0.0", "1.1.0")

# (row label in the report, aggregate key, lower is better)
METRICS = [
    ("Route accuracy", "route_accuracy", False),
    ("Section 4.1 case reaches FSS-AC-2018", "s41_claim_finding", False),
    ("Mean tool calls per run", "mean_tool_calls", True),
    ("Groundedness / faithfulness", ("groundedness", "faithfulness"), False),
]
EXTRA = [("Hallucination rate", "hallucination_rate", True), ("Unsafe clear rate", "unsafe_clear_rate", True),
         ("Citation resolution", "citation_resolution", False), ("Mean LLM calls per run", "mean_llm_calls", True),
         ("Mean cost per run (USD)", "mean_cost_usd", True)]


def tag(version: str) -> str:
    return f"researcher-{version}"


def load(version: str, out_dir: Path = RESULTS) -> dict:
    path = out_dir / f"{tag(version)}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run `python -m fssai_agents.compare run` first")
    return json.loads(path.read_text(encoding="utf-8"))


def s41_claim_finding(results: dict) -> float | None:
    """Share of the section 4.1 scenarios in which the researcher produced a finding for the claim's own requirement.

    The claim condition lives in FSS-AC-2018, so a claim finding with a status means the search got there. (The rows
    do not store the trace; `faithfulness` and `citation_resolution` cover whether the finding was grounded.)"""
    rows = [r for r in results["scenarios"] if "section-4.1" in r.get("tags", []) and not r.get("error")
            and not r.get("provider_failed")]
    if not rows:
        return None
    hits = 0
    for r in rows:
        claim = [e for rid, e in r.get("expected_findings", {}).items() if rid.startswith("CLM-")]
        hits += bool(claim) and all(e.get("got") is not None for e in claim)
    return hits / len(rows)


def value(results: dict, key) -> float | str | None:
    agg = results["aggregate"]
    if key == "s41_claim_finding":
        return s41_claim_finding(results)
    if isinstance(key, tuple):
        a, b = (agg.get(k) for k in key)
        return None if a is None or b is None else f"{a:.2f} / {b:.2f}"
    return agg.get(key)


def fmt(v) -> str:
    return "n/a" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def difference(a, b, lower_better: bool) -> str:
    if isinstance(a, str) or isinstance(b, str):
        if not (isinstance(a, str) and isinstance(b, str)):
            return "n/a"
        (ga, fa), (gb, fb) = (tuple(map(float, x.split(" / "))) for x in (a, b))
        return f"{gb - ga:+.2f} / {fb - fa:+.2f}"
    if a is None or b is None:
        return "n/a"
    d = b - a
    return "0" if d == 0 else f"{d:+.2f}"


def verdict(before: dict, after: dict) -> tuple[str, list[str]]:
    """Which variant is better, decided on safety first, then correctness, then cost. Returns (winner, reasons)."""
    reasons: list[str] = []
    score = {"1.0.0": 0, "1.1.0": 0}
    ordered = [("unsafe_clear_rate", True), ("hallucination_rate", True), ("route_accuracy", False),
               ("finding_accuracy", False), ("groundedness", False), ("mean_tool_calls", True)]
    for key, lower in ordered:
        a, b = before["aggregate"].get(key), after["aggregate"].get(key)
        if a is None or b is None or a == b:
            continue
        better = "1.1.0" if (b < a) == lower else "1.0.0"
        score[better] += 1
        reasons.append(f"{key}: {fmt(a)} (1.0.0) vs {fmt(b)} (1.1.0), {better} better")
        if key in ("unsafe_clear_rate", "hallucination_rate"):  # a safety metric decides on its own
            return better, reasons
    if score["1.0.0"] == score["1.1.0"]:
        return "tie", reasons or ["no metric differed"]
    return ("1.1.0" if score["1.1.0"] > score["1.0.0"] else "1.0.0"), reasons


def table(before: dict, after: dict, rows=METRICS) -> str:
    lines = ["| Metric | 1.0.0 | 1.1.0 | Difference |", "|---|---|---|---|"]
    for label, key, lower in rows:
        a, b = value(before, key), value(after, key)
        lines.append(f"| {label} | {fmt(a)} | {fmt(b)} | {difference(a, b, lower)} |")
    return "\n".join(lines)


def fill_report(text: str, before: dict, after: dict, winner: str, reasons: list[str]) -> str:
    start = text.index("| Metric | 1.0.0 | 1.1.0 | Difference |")
    end = text.index("\n\n", start)
    text = text[:start] + table(before, after) + text[end:]
    result = re.compile(r"^Result: .*$", re.M)
    sentence = ("Result: " + (f"researcher {winner} was better. " if winner != "tie" else "no clear winner. ")
                + "; ".join(reasons[:3]) + f" (n = {before['aggregate']['scenarios']} / {after['aggregate']['scenarios']} scenarios; "
                "see `docs/decisions/103-namith-prompt-comparison.md`).")
    return result.sub(lambda _m: sentence, text, count=1)


def decision_record(before: dict, after: dict, winner: str, reasons: list[str]) -> str:
    cfg = after.get("config", {})
    return f"""# 103: Researcher prompt comparison, 1.0.0 against 1.1.0 (Namith)

Status: measured {after.get('created_at', '')[:10]}. Requirements: L2 (versioned prompts, two variants compared), L3.

## Context

Two versions of the researcher prompt (with its paired draft prompt) exist: 1.0.0 (plain rules) and 1.1.0 (adds an
explicit checklist for provisions that modify, condition or exempt another). Both were run through the same evaluation
set (`packages/eval/scenarios.jsonl`, {after['aggregate']['scenarios']} scenarios completed in 1.1.0,
{before['aggregate']['scenarios']} in 1.0.0), the same model, retriever, verifier, router and limits. Only
`PROMPT_RESEARCHER_VERSION` and `PROMPT_RESEARCHER_DRAFT_VERSION` differed. Results: `packages/eval/results/{tag('1.0.0')}.json`
and `{tag('1.1.0')}.json` (judge: {after.get('judge')}; git sha {before.get('git_sha', '?')} / {after.get('git_sha', '?')}).

## Result

{table(before, after, METRICS + EXTRA)}

Verdict: **{winner}**. {' '.join(r + '.' for r in reasons) if reasons else ''}

Safety metrics decide first (a prompt that clears labels it should not, or states unsupported things, loses whatever
else it gains), then correctness, then cost. Scenarios cut short by the provider's rate limit are counted separately
and never scored (`provider_failures`: {before['aggregate'].get('provider_failures')} / {after['aggregate'].get('provider_failures')}).

## What this does and does not show

- With {after['aggregate']['scenarios']} scenarios, a difference of one scenario is {100 / max(after['aggregate']['scenarios'], 1):.1f} points
  of route accuracy. Treat small gaps as noise.
- Each variant ran once; a free-tier model is not deterministic, so a rerun can differ.
- The section 4.1 finding stays `cannot_determine` until the RDA reference value is decided (team question), so that
  row measures whether the claim was researched, not whether it was decided.

## Decision

TODO (Namith): keep {winner if winner != 'tie' else 'the newer variant or the cheaper one'} as the default and say why in one sentence; record
`PROMPT_RESEARCHER_VERSION` in `.env.example` if it is pinned.
"""


def _run(args) -> int:
    versions = [args.only] if args.only else list(VARIANTS)
    for version in versions:
        if version not in VARIANTS:
            print(f"unknown variant {version}; known: {', '.join(VARIANTS)}")
            return 2
        env = dict(os.environ, PROMPT_RESEARCHER_VERSION=version, PROMPT_RESEARCHER_DRAFT_VERSION=version)
        cmd = [sys.executable, "-m", "fssai_eval", "run", "--tag", tag(version), "--pause-s", str(args.pause_s),
               "--resume"] + (["--judge", args.judge] if args.judge else [])
        print(f"== researcher {version}: {' '.join(cmd)}")
        code = subprocess.run(cmd, cwd=ROOT, env=env).returncode
        if code:
            print(f"researcher {version} did not finish (exit {code}); rerun the same command to resume")
            return code
    return 0


def _report(args) -> int:
    before, after = load("1.0.0", args.out_dir), load("1.1.0", args.out_dir)
    winner, reasons = verdict(before, after)
    print(table(before, after, METRICS + EXTRA))
    print(f"\nverdict: {winner}")
    for r in reasons:
        print(" -", r)
    if args.write:
        REPORT.write_text(fill_report(REPORT.read_text(encoding="utf-8"), before, after, winner, reasons), encoding="utf-8")
        DECISION.write_text(decision_record(before, after, winner, reasons), encoding="utf-8")
        print(f"\nwrote {REPORT.relative_to(ROOT)} and {DECISION.relative_to(ROOT)} (finish the Decision paragraph by hand)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m fssai_agents.compare", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the eval set once per prompt variant")
    r.add_argument("--only", choices=VARIANTS, default=None)
    r.add_argument("--pause-s", type=float, default=60.0, help="seconds between scenarios (free-tier token limit)")
    r.add_argument("--judge", default=None, help="reference | llm | trulens (default: the runner's)")
    q = sub.add_parser("report", help="table and verdict from the two results files")
    q.add_argument("--write", action="store_true", help="fill docs/report/agent-design.md and write decision 103")
    q.add_argument("--out-dir", type=Path, default=RESULTS)
    args = p.parse_args(argv)
    return _run(args) if args.cmd == "run" else _report(args)


if __name__ == "__main__":
    sys.exit(main())
