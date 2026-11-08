"""Checkpointing (Namith's extra): a run interrupted mid-graph resumes at the interrupted node, with its trace.

A dead worker is simulated by a node that raises an exception nothing catches: like a process that dies, it leaves
the checkpoint behind. The same run id then runs again with a fresh RunContext, as the re-queued job would.
The Postgres test needs FSSAI_TEST_DATABASE_URL (CI has one), like the run store's tests.
"""
import os

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fssai_agents import checkpoints
from fssai_agents.graph import LangGraphPipeline
from fssai_contracts.context import RunContext
from fssai_contracts.fakes import FakeClassifier, FakeGuardrails, FakeResearcher, FakeRouter, FakeVerifier
from fssai_contracts.schemas import Classification, ResearchDossier, Route

from .test_contract_parity import make_request, view

URL = os.environ.get("FSSAI_TEST_DATABASE_URL", "")


class WorkerDied(Exception):
    """Stands in for SIGKILL: nothing in the pipeline catches it."""


class CountingClassifier(FakeClassifier):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def classify(self, request, ctx):
        self.calls += 1
        return super().classify(request, ctx)


class DiesOnce(FakeResearcher):
    """Researcher whose first call 'kills the worker' after doing part of its work."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def research(self, request, classification, ctx, retry_hint=None, previous=None):
        self.calls += 1
        if self.calls == 1:
            ctx.record(agent="researcher", kind="tool", name="corpus_search", output={"passages": []})
            raise WorkerDied("worker killed mid-research")
        return super().research(request, classification, ctx, retry_hint=retry_hint, previous=previous)


def pipeline(checkpointer, **parts):
    base = dict(guardrails=FakeGuardrails(), classifier=FakeClassifier(), researcher=FakeResearcher(),
                verifier=FakeVerifier(), router=FakeRouter())
    base.update(parts)
    return LangGraphPipeline(**base, checkpointer=checkpointer)


def saved(p, run_id):
    return p.graph.get_state({"configurable": {"thread_id": run_id}}).values


def test_results_are_the_same_with_and_without_checkpoints():
    request = make_request()
    plain = pipeline(None).run(request, RunContext.new())
    checked = pipeline(InMemorySaver(serde=checkpoints.serializer())).run(request, RunContext.new())
    assert view(checked) == view(plain)


def test_a_finished_run_deletes_its_checkpoint():
    p = pipeline(InMemorySaver(serde=checkpoints.serializer()))
    ctx = RunContext.new()
    p.run(make_request(), ctx)
    assert saved(p, ctx.run_id) == {}


def test_an_interrupted_run_resumes_at_the_interrupted_node():
    classifier, researcher = CountingClassifier(), DiesOnce()
    p = pipeline(InMemorySaver(serde=checkpoints.serializer()), classifier=classifier, researcher=researcher)
    request, run_id = make_request(), "a" * 32

    with pytest.raises(WorkerDied):
        p.run(request, RunContext.new(run_id=run_id))
    state = saved(p, run_id)
    assert isinstance(state["classification"], Classification), "the checkpoint holds contract models"
    assert state["dossier"] is None and state["attempts"] == 0
    done_before = [(s.agent, s.kind) for s in state["steps"]]
    assert ("researcher", "tool") not in done_before, "the unfinished node's steps are not checkpointed"

    ctx = RunContext.new(run_id=run_id)  # the re-queued job: a new process, a new context
    result = p.run(request, ctx)

    assert classifier.calls == 1, "the classifier is not called again"
    assert researcher.calls == 2
    assert result.complete and result.routing.route == Route.CLEAR_FOR_PRINT
    kinds = [(s.agent, s.kind) for s in result.steps]
    assert kinds[:len(done_before)] == done_before, "the trace starts with the steps restored from the checkpoint"
    assert [s.step_index for s in result.steps] == list(range(len(result.steps)))
    assert saved(p, run_id) == {}


def test_resumed_run_counts_restored_steps_against_the_budget():
    p = pipeline(InMemorySaver(serde=checkpoints.serializer()), researcher=DiesOnce())
    request, run_id = make_request(), "b" * 32
    with pytest.raises(WorkerDied):
        p.run(request, RunContext.new(run_id=run_id))
    before = len(saved(p, run_id)["steps"])
    ctx = RunContext.new(run_id=run_id)
    assert before > 0
    result = p.run(request, ctx)
    assert result.totals.steps == len(ctx.steps) > before, "steps done before the interruption count in the totals"


def test_a_different_request_under_the_same_id_starts_fresh():
    classifier = CountingClassifier()
    p = pipeline(InMemorySaver(serde=checkpoints.serializer()), classifier=classifier, researcher=DiesOnce())
    run_id = "c" * 32
    with pytest.raises(WorkerDied):
        p.run(make_request(protein_g=12.0), RunContext.new(run_id=run_id))
    result = p.run(make_request(protein_g=3.0), RunContext.new(run_id=run_id))
    assert classifier.calls == 2, "a checkpoint for another request is discarded, never continued"
    assert result.complete


def test_a_graph_that_finished_before_the_save_returns_its_saved_result(monkeypatch):
    researcher = FakeResearcher()
    p = pipeline(InMemorySaver(serde=checkpoints.serializer()), researcher=researcher)
    request, run_id = make_request(), "d" * 32
    monkeypatch.setattr(p, "_forget", lambda run_id: None)  # the worker died between the graph's end and the save
    first = p.run(request, RunContext.new(run_id=run_id))
    monkeypatch.undo()

    calls = []
    monkeypatch.setattr(researcher, "research", lambda *a, **k: calls.append(1) or ResearchDossier())
    again = p.run(request, RunContext.new(run_id=run_id))
    assert calls == [], "nothing runs again"
    assert view(again) == view(first)
    assert saved(p, run_id) == {}


def test_the_serializer_only_rebuilds_contract_types():
    names = {t.__name__ for t in checkpoints.schema_types()}
    assert {"LabelCheckRequest", "StepRecord", "ResearchDossier", "Verdict", "Route"} <= names
    assert all(t.__module__ == "fssai_contracts.schemas" for t in checkpoints.schema_types())


@pytest.mark.parametrize("value", ["", "off", "0"])
def test_checkpoints_are_off_by_default(value):
    assert checkpoints.from_env({"PIPELINE_CHECKPOINTS": value}) is None
    assert checkpoints.from_env({}) is None


def test_memory_checkpoints_from_env():
    assert isinstance(checkpoints.from_env({"PIPELINE_CHECKPOINTS": "memory  # in-process"}), InMemorySaver)


def test_bad_checkpoint_settings_fail_at_start_up():
    with pytest.raises(RuntimeError, match="must be empty"):
        checkpoints.from_env({"PIPELINE_CHECKPOINTS": "sqlite"})
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        checkpoints.from_env({"PIPELINE_CHECKPOINTS": "postgres"})


def test_an_unreachable_checkpoint_database_turns_checkpoints_off(caplog):
    url = "postgresql://nobody:x@127.0.0.1:1/none?connect_timeout=1"
    assert checkpoints.from_env({"PIPELINE_CHECKPOINTS": "postgres", "DATABASE_URL": url}) is None
    assert "checkpoints_off" in caplog.text


@pytest.mark.skipif(not URL, reason="set FSSAI_TEST_DATABASE_URL to a disposable Postgres")
def test_postgres_checkpoints_survive_a_new_pipeline_process():
    """Two pipelines with two savers on the same database stand in for the dead worker and the one that takes over."""
    request, run_id = make_request(), os.urandom(16).hex()
    first = pipeline(checkpoints.from_env({"PIPELINE_CHECKPOINTS": "postgres", "DATABASE_URL": URL}),
                     researcher=DiesOnce())
    with pytest.raises(WorkerDied):
        first.run(request, RunContext.new(run_id=run_id))

    classifier = CountingClassifier()
    second = pipeline(checkpoints.from_env({"PIPELINE_CHECKPOINTS": "postgres", "DATABASE_URL": URL}),
                      classifier=classifier)
    assert saved(second, run_id)["attempts"] == 0
    result = second.run(request, RunContext.new(run_id=run_id))
    assert classifier.calls == 0, "the new process continues at research; classification came from the checkpoint"
    assert result.complete and result.routing.route == Route.CLEAR_FOR_PRINT
    assert saved(second, run_id) == {}


def test_a_run_interrupted_inside_the_real_researcher_resumes():
    """The researcher is a LangGraph graph of its own whose state holds the live RunContext. It must never inherit
    the pipeline's checkpointer, or a resume rebuilds that context as a plain dict (found on the stack, 8 Nov)."""
    from .test_researcher import ScriptedLLM, draft, protein_finding, researcher

    llm = ScriptedLLM(drafts=[WorkerDied("killed while drafting"), draft(protein_finding())])
    classifier = CountingClassifier()
    p = pipeline(InMemorySaver(serde=checkpoints.serializer()), classifier=classifier, researcher=researcher(llm))
    request, run_id = make_request(), "e" * 32
    with pytest.raises(WorkerDied):
        p.run(request, RunContext.new(run_id=run_id))
    result = p.run(request, RunContext.new(run_id=run_id))
    assert classifier.calls == 1
    assert result.complete and result.findings, "the resumed research attempt ran from its start and finished"
