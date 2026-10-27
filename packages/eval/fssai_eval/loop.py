"""Two extras that close the loop between live use and the eval set.

candidates  feedback -> candidate scenarios: every unsatisfactory feedback becomes a *draft* EvalScenario with the
            run's request, in packages/eval/candidates.jsonl, tagged needs-review. A person sets the expected route and
            findings (and real supporting quotes) before moving it into scenarios.jsonl; nothing is added to the
            eval set automatically, because an unreviewed "expected answer" would be invented.
calibrate   LLM-judge calibration: compare the judge's support decisions with hand labels and report raw agreement
            and Cohen's kappa. `template` writes items to label (statement + the text it cites, human_label null);
            `score` reads the labelled file.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import EvalScenario, Route, utcnow

from .judges import Judge, make_judge
from .metrics import retrieved_passages


# ---------------------------------------------------------------- feedback -> candidate scenarios

def feedback_rows(days: int, feedback_file: Path | None) -> list[dict]:
    if feedback_file:
        return [json.loads(x) for x in feedback_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    url = os.environ.get("DATABASE_URL", "").split("#", 1)[0].strip()
    if not url:
        raise RuntimeError("set DATABASE_URL (the feedback table) or pass --feedback-file")
    import psycopg
    with psycopg.connect(url, connect_timeout=5) as conn:
        rows = conn.execute("SELECT run_id, satisfactory, reason, route, submitted_at FROM feedback "
                            "WHERE submitted_at >= %s ORDER BY submitted_at", (utcnow() - timedelta(days=days),))
        return [dict(zip(("run_id", "satisfactory", "reason", "route", "submitted_at"), r)) for r in rows]


def candidates(rows: list[dict], run_store, existing: set[str]) -> list[EvalScenario]:
    out: dict[str, EvalScenario] = {}
    for fb in rows:
        if fb.get("satisfactory"):
            continue
        sid = f"fb-{fb['run_id'][:12]}"
        if sid in existing or sid in out:
            continue
        status = run_store.get(fb["run_id"])
        if status is None or status.request is None:
            continue
        got = status.result.routing.route.value if status.result else fb.get("route")
        out[sid] = EvalScenario(
            scenario_id=sid, tags=["from-feedback", "needs-review"], request=status.request,
            # placeholder only: a reviewer replaces it. regulatory-review is the conservative default (F7).
            expected_route=Route.REGULATORY_REVIEW, expected_findings={}, supporting=[],
            description=f"From feedback on run {fb['run_id']} (routed {got}): \"{str(fb.get('reason', ''))[:300]}\". "
                        "REVIEW: set expected_route, expected_findings and supporting quotes before use.")
    return list(out.values())


# ---------------------------------------------------------------- judge calibration

def cohens_kappa(a: list[bool], b: list[bool]) -> float | None:
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else round((po - pe) / (1 - pe), 4)


def calibration_template(scenarios: list[EvalScenario], limit: int, pipeline=None) -> list[dict]:
    """Statements the pipeline makes on the eval set, each with the text it cites, for a person to label."""
    from fssai_contracts.registry import build
    pipeline = pipeline or build("pipeline")
    items: list[dict] = []
    for s in scenarios:
        result = pipeline.run(s.request, RunContext.new())
        passages = retrieved_passages(result)
        for f in result.findings:
            cited = [passages[c.passage_id] for c in f.citations if c.passage_id in passages]
            if not cited:
                continue
            items.append({"item_id": f"{s.scenario_id}:{f.requirement_id}",
                          "statement": f"{f.requirement}: {f.status.value}. {f.explanation}",
                          "source": "\n\n".join(f"[{p.regulation.value} {p.clause_id}] {p.text}" for p in cited),
                          "human_label": None})
            if len(items) >= limit:
                return items
    return items


def calibration_score(items: list[dict], judge: Judge | None = None) -> dict:
    judge = judge or make_judge("llm")
    labelled = [i for i in items if i.get("human_label") in ("supported", "unsupported")]
    human, model, rows = [], [], []
    for i in labelled:
        score = judge.support(i["statement"], i["source"])
        if score is None:
            continue
        human.append(i["human_label"] == "supported")
        model.append(score >= 0.5)
        rows.append({"item_id": i["item_id"], "human": i["human_label"], "judge_score": round(score, 3)})
    agree = sum(h == m for h, m in zip(human, model))
    return {"judge": judge.name, "labelled": len(labelled), "judged": len(human),
            "agreement": round(agree / len(human), 4) if human else None, "cohens_kappa": cohens_kappa(human, model),
            "confusion": {"both_supported": sum(h and m for h, m in zip(human, model)),
                          "both_unsupported": sum(not h and not m for h, m in zip(human, model)),
                          "judge_only_supported": sum(m and not h for h, m in zip(human, model)),
                          "human_only_supported": sum(h and not m for h, m in zip(human, model))},
            "items": rows}
