"""Live scoring (L6): score a sample of recently completed runs with the eval metrics, store them in quality_scores.

    python -m fssai_eval live --sample 10 [--judge llm] [--every 300]

Reads runs through the RunStore seam (IMPL_RUN_STORE; Postgres in Compose), skips runs this scorer version has
already scored, and writes one quality_scores row per run (infra/postgres/init/22-vihaan-quality-scores.sql).
Live runs have no expected answer, so only the reference-free metrics apply: groundedness, context relevance
(needs a model judge; the offline judge has no gold clauses to compare with), faithfulness, hallucination and
citation resolution. Without DATABASE_URL the scores are printed instead of stored.
"""
from __future__ import annotations

import json
import logging
import os
import time

from fssai_contracts.schemas import RunState, RunStatus, utcnow

from .judges import Judge, make_judge
from .metrics import ResponseScore, score_response

log = logging.getLogger("fssai.eval.live")
SCORER_VERSION = "1"

_INSERT = """
INSERT INTO quality_scores (run_id, scorer_version, scored_at, run_updated_at, route, complete, groundedness,
                            context_relevance, faithfulness, hallucinated, citation_resolution, judge, detail)
VALUES (%(run_id)s, %(scorer_version)s, %(scored_at)s, %(run_updated_at)s, %(route)s, %(complete)s,
        %(groundedness)s, %(context_relevance)s, %(faithfulness)s, %(hallucinated)s, %(citation_resolution)s,
        %(judge)s, %(detail)s)
ON CONFLICT (run_id, scorer_version) DO NOTHING
"""


def _env(name: str) -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip()


class PostgresScores:
    def __init__(self, url: str) -> None:
        import psycopg
        self.conn = psycopg.connect(url, autocommit=True, connect_timeout=5)

    def scored(self, version: str) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT run_id FROM quality_scores WHERE scorer_version = %s",
                                                (version,)).fetchall()}

    def write(self, rows: list[dict]) -> None:
        from psycopg.types.json import Jsonb
        with self.conn.cursor() as cur:
            cur.executemany(_INSERT, [{**r, "detail": Jsonb(r["detail"])} for r in rows])


class PrintScores:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def scored(self, version: str) -> set[str]:
        return {r["run_id"] for r in self.rows}

    def write(self, rows: list[dict]) -> None:
        self.rows += rows
        for r in rows:
            print(json.dumps(r, default=str))


def sink_from_env():
    url = _env("DATABASE_URL")
    if url:
        try:
            return PostgresScores(url)
        except Exception as exc:  # noqa: BLE001 - no database here: still useful as a printout
            log.warning("quality_scores unavailable (%s); printing scores instead", type(exc).__name__)
    return PrintScores()


def pick(runs: list[RunStatus], already: set[str], sample: int) -> list[RunStatus]:
    """Newest completed runs with a request and a result that this scorer version has not scored."""
    done = [r for r in runs if r.state == RunState.COMPLETED and r.result is not None and r.request is not None
            and r.run_id not in already]
    return sorted(done, key=lambda r: r.updated_at, reverse=True)[:sample]


def to_row(status: RunStatus, score: ResponseScore, judge: Judge) -> dict:
    return {"run_id": status.run_id, "scorer_version": f"{judge.name}-{SCORER_VERSION}", "scored_at": utcnow(),
            "run_updated_at": status.updated_at, "route": score.route, "complete": score.complete,
            "groundedness": score.groundedness, "context_relevance": score.context_relevance,
            "faithfulness": score.faithfulness, "hallucinated": score.hallucinated,
            "citation_resolution": score.citation_resolution, "judge": judge.name,
            "detail": {"statements": [s.__dict__ for s in score.statements], "passages": score.passages_retrieved}}


def score_once(store, sink, judge: Judge, sample: int) -> list[dict]:
    version = f"{judge.name}-{SCORER_VERSION}"
    chosen = pick(store.recent(limit=max(50, sample * 5)), sink.scored(version), sample)
    rows = [to_row(s, score_response(s.result, s.request, judge), judge) for s in chosen]
    if rows:
        sink.write(rows)
    log.info(json.dumps({"event": "live_scored", "runs": len(rows), "judge": judge.name}))
    return rows


def main(sample: int, judge_name: str | None, every_s: float | None) -> int:
    from fssai_contracts.registry import build

    store, sink, judge = build("run_store"), sink_from_env(), make_judge(judge_name)
    while True:
        try:
            rows = score_once(store, sink, judge, sample)
            print(f"scored {len(rows)} run(s) with judge={judge.name}")
        except Exception as exc:  # noqa: BLE001 - a periodic scorer logs and tries again next round
            log.warning("live scoring failed: %s: %s", type(exc).__name__, exc)
            if every_s is None:
                return 1
        if every_s is None:
            return 0
        time.sleep(every_s)
