"""Live scoring, feedback -> candidate scenarios, and judge calibration (Cohen's kappa)."""
from fssai_contracts.context import RunContext
from fssai_contracts.conformance import sample_request
from fssai_contracts.fakes import InMemoryRunStore
from fssai_contracts.pipeline import ReferencePipeline
from fssai_contracts.schemas import RunState, RunStatus, utcnow
from fssai_eval.judges import ReferenceJudge
from fssai_eval.live import PrintScores, pick, score_once
from fssai_eval.loop import calibration_score, candidates, cohens_kappa


def stored_run(store, state=RunState.COMPLETED, protein=12.0):
    req = sample_request(protein_g=protein)
    ctx = RunContext.new()
    res = ReferencePipeline.from_registry().run(req, ctx) if state == RunState.COMPLETED else None
    now = utcnow()
    store.save(RunStatus(run_id=ctx.run_id, state=state, submitted_at=now, updated_at=now, request=req, result=res))
    return ctx.run_id


def test_live_scores_new_completed_runs_once():
    store, sink = InMemoryRunStore(), PrintScores()
    a, b = stored_run(store), stored_run(store)
    stored_run(store, state=RunState.QUEUED)
    rows = score_once(store, sink, ReferenceJudge(), sample=10)
    assert {r["run_id"] for r in rows} == {a, b}
    assert all(r["scorer_version"] == "reference-1" and r["citation_resolution"] == 1.0 for r in rows)
    assert score_once(store, sink, ReferenceJudge(), sample=10) == [], "never scores a run twice"


def test_pick_takes_the_newest_sample():
    store = InMemoryRunStore()
    ids = [stored_run(store) for _ in range(4)]
    assert [s.run_id for s in pick(store.recent(), set(), 2)] == ids[::-1][:2]


def test_unsatisfactory_feedback_becomes_a_draft_scenario():
    store = InMemoryRunStore()
    run_id = stored_run(store)
    rows = [{"run_id": run_id, "satisfactory": False, "reason": "Missed the veg mark"},
            {"run_id": run_id, "satisfactory": False, "reason": "again"},
            {"run_id": stored_run(store), "satisfactory": True, "reason": "fine"},
            {"run_id": "f" * 32, "satisfactory": False, "reason": "unknown run"}]
    new = candidates(rows, store, existing=set())
    assert len(new) == 1
    s = new[0]
    assert s.scenario_id == f"fb-{run_id[:12]}" and "needs-review" in s.tags and "Missed the veg mark" in s.description
    assert s.request == store.get(run_id).request
    assert candidates(rows, store, existing={s.scenario_id}) == []


def test_cohens_kappa():
    assert cohens_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert cohens_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert cohens_kappa([], []) is None


def test_calibration_score_counts_only_labelled_items():
    class Judge:
        name = "scripted"

        def support(self, statement, source):
            return 1.0 if "yes" in statement else 0.0
    items = [{"item_id": "1", "statement": "yes", "source": "s", "human_label": "supported"},
             {"item_id": "2", "statement": "no", "source": "s", "human_label": "unsupported"},
             {"item_id": "3", "statement": "yes", "source": "s", "human_label": "unsupported"},
             {"item_id": "4", "statement": "yes", "source": "s", "human_label": None}]
    out = calibration_score(items, Judge())
    assert out["labelled"] == 3 and out["agreement"] == round(2 / 3, 4) and out["confusion"]["judge_only_supported"] == 1
