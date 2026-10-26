"""Run the eval set through the configured pipeline in-process and write eval/results/<tag>.json (V3.2).

The pipeline comes from build("pipeline"), so whatever IMPL_* switches are set is what gets measured: the fakes
today, the LangGraph pipeline with the real retriever and gateway once they are on. Scenarios run one at a time
(free-tier rate limits); each gets a fresh RunContext with the usual loop bounds.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import EvalScenario, utcnow

from .judges import Judge, make_judge
from .metrics import DEFINITIONS, ResponseScore, aggregate, score_response

RESULTS = Path("eval/results")


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [EvalScenario.model_validate_json(line) for line in lines if line.strip()]


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def config_snapshot() -> dict:
    """What was measured: every switch and setting that changes behaviour, never a secret (D4)."""
    keep = ("IMPL_", "PROMPT_", "RETRIEVAL_", "RESEARCHER_", "VERIFIER_", "RUN_MAX_", "EMBEDDING_MODEL",
            "CHUNK_MAX_CHARS", "CORPUS_CATEGORIES", "EVAL_JUDGE")
    secret = ("KEY", "PASSWORD", "SECRET", "TOKEN", "URL")
    return {k: v.split("#", 1)[0].strip() for k, v in sorted(os.environ.items())
            if k.startswith(keep) and not any(s in k for s in secret)}


def _provider_failed(result) -> bool:
    """The pipeline turns ProviderUnavailable into an incomplete run (pipeline.py); that is quota, not quality."""
    return not result.complete and "ProviderUnavailable" in (result.routing.escalation_reason or "")


def _row(d: dict) -> ResponseScore:
    from .metrics import StatementScore
    return ResponseScore(**{**d, "statements": [StatementScore(**s) for s in d.get("statements", [])]})


def run_eval(scenarios: list[EvalScenario], tag: str, *, judge: Judge | None = None, pipeline=None,
             only: set[str] | None = None, progress: Callable[[str], None] | None = None, pause_s: float = 0.0,
             resume: dict | None = None, checkpoint: Callable[[dict], None] | None = None) -> dict:
    """pause_s: seconds between scenarios that call the pipeline (a free tier's tokens-per-minute limit).
    resume: an earlier results dict for the same tag; its scored rows are kept and only errors and provider
    failures run again. checkpoint: called with the results so far after every scenario (write them to disk)."""
    from fssai_contracts.registry import build

    judge = judge or make_judge()
    pipeline = pipeline or build("pipeline")
    kept = {r["scenario_id"]: _row(r) for r in (resume or {}).get("scenarios", [])
            if r.get("error") is None and not r.get("provider_failed")}
    rows: list[ResponseScore] = []
    prompt_versions: dict[str, str] = dict((resume or {}).get("prompt_versions", {}))
    started = time.monotonic()
    todo = [s for s in scenarios if not only or s.scenario_id in only]

    def results() -> dict:
        return {
            "tag": tag, "created_at": utcnow().isoformat(), "git_sha": _git_sha(),
            "judge": judge.name, "judge_calls": getattr(judge, "calls", 0),
            "config": config_snapshot(), "prompt_versions": prompt_versions,
            "elapsed_s": round(time.monotonic() - started, 2),
            "aggregate": aggregate(rows), "definitions": DEFINITIONS,
            "scenarios": [r.as_dict() for r in rows],
        }

    ran_one = False
    for s in todo:
        if s.scenario_id in kept:
            rows.append(kept[s.scenario_id])
            continue
        if ran_one and pause_s > 0:
            time.sleep(pause_s)
        ran_one = True
        ctx = RunContext.new()
        try:
            result = pipeline.run(s.request, ctx)
            row = score_response(result, s.request, judge, s)
            row.provider_failed = _provider_failed(result)
            prompt_versions.update(result.prompt_versions)
        except Exception as exc:  # noqa: BLE001 - one broken scenario must not hide the other results
            row = ResponseScore(scenario_id=s.scenario_id, route=None, expected_route=s.expected_route.value,
                                complete=None, error=f"{type(exc).__name__}: {exc}", tags=list(s.tags))
        rows.append(row)
        if progress:
            mark = ("ERR" if row.error else "429" if row.provider_failed
                    else "ok " if row.route == row.expected_route else "-- ")
            progress(f"{mark} {s.scenario_id:32s} {row.route or row.error} (expected {row.expected_route})")
        if checkpoint:
            checkpoint(results())
    return results()


def write_results(results: dict, out_dir: Path = RESULTS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{results['tag']}.json"
    path.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def load_results(tag_or_path: str, out_dir: Path = RESULTS) -> dict:
    p = Path(tag_or_path)
    if not p.suffix:
        p = out_dir / f"{tag_or_path}.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- reporting

HEADLINE = ["groundedness", "context_relevance", "faithfulness", "hallucination_rate", "route_accuracy",
            "finding_accuracy", "escalation_recall", "unsafe_clear_rate", "citation_resolution",
            "mean_llm_calls", "mean_tool_calls", "mean_cost_usd"]
LOWER_IS_BETTER = {"hallucination_rate", "unsafe_clear_rate", "mean_cost_usd", "mean_llm_calls", "mean_tool_calls"}


def _fmt(v) -> str:
    return "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def summary_table(results: dict) -> str:
    a = results["aggregate"]
    lines = [f"eval '{results['tag']}' ({a['scenarios']} scenarios, {a['errors']} errors, judge={results['judge']})",
             f"{'metric':22s} value"]
    lines += [f"{m:22s} {_fmt(a.get(m))}" for m in HEADLINE]
    lines.append(f"{'faithfulness coverage':22s} {a['faithfulness_coverage']}")
    return "\n".join(lines)


def compare(a: dict, b: dict) -> str:
    """Before/after table with deltas (V3.3), plus every scenario whose route changed."""
    lines = [f"{'metric':22s} {a['tag'][:14]:>14s} {b['tag'][:14]:>14s} {'delta':>9s}"]
    for m in HEADLINE:
        va, vb = a["aggregate"].get(m), b["aggregate"].get(m)
        delta = "" if not (isinstance(va, (int, float)) and isinstance(vb, (int, float))) else f"{vb - va:+.3f}"
        better = ""
        if delta and vb != va:
            better = " better" if (vb < va) == (m in LOWER_IS_BETTER) else " worse"
        lines.append(f"{m:22s} {_fmt(va):>14s} {_fmt(vb):>14s} {delta:>9s}{better}")
    before = {r["scenario_id"]: r for r in a["scenarios"]}
    changed = [(sid, before[sid]["route"], r["route"], r["expected_route"]) for r in b["scenarios"]
               if (sid := r["scenario_id"]) in before and before[sid]["route"] != r["route"]]
    if changed:
        lines.append("\nroute changes (scenario: before -> after, expected):")
        lines += [f"  {sid}: {x} -> {y} (expected {e})" for sid, x, y, e in changed]
    return "\n".join(lines)


def regression_gate(baseline: dict, candidate: dict, *, max_hallucination_increase: float = 0.0,
                    max_route_accuracy_drop: float = 0.05, max_unsafe_clear_increase: float = 0.0) -> list[str]:
    """Reasons the candidate is worse than the baseline; empty means it passes (extra: eval as a CI gate)."""
    a, b = baseline["aggregate"], candidate["aggregate"]
    fails = []
    ha, hb = a.get("hallucination_rate") or 0.0, b.get("hallucination_rate") or 0.0
    if hb > ha + max_hallucination_increase:
        fails.append(f"hallucination rate rose {ha:.3f} -> {hb:.3f}")
    ra, rb = a.get("route_accuracy") or 0.0, b.get("route_accuracy") or 0.0
    if rb < ra - max_route_accuracy_drop:
        fails.append(f"route accuracy fell {ra:.3f} -> {rb:.3f} (more than {max_route_accuracy_drop:.2f})")
    ua, ub = a.get("unsafe_clear_rate") or 0.0, b.get("unsafe_clear_rate") or 0.0
    if ub > ua + max_unsafe_clear_increase:
        fails.append(f"unsafe clear rate rose {ua:.3f} -> {ub:.3f}: more labels cleared that should not have been")
    if b.get("errors"):
        fails.append(f"{b['errors']} scenario(s) raised instead of returning a result")
    return fails
