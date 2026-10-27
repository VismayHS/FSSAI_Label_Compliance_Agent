"""The demo rehearsal checks (M4.1): citation resolution against the trace, and the injection evidence."""
from fssai_agents import demo

PASSAGE = {"passage_id": "p1", "regulation": "FSS-AC-2018", "clause_id": "Sch-I-11",
           "text": "A claim of 'source' of protein may be made when the food contains 10 per cent of RDA per 100 g."}
STEPS = [{"kind": "tool", "name": "corpus_search", "output": {"passages": [PASSAGE]}}]


def cite(**over):
    return {"passage_id": "p1", "regulation": "FSS-AC-2018", "clause_id": "Sch-I-11",
            "quote": "contains 10 per cent of RDA per 100 g", **over}


def report(*citations, steps=STEPS):
    return demo.citation_report([{"requirement_id": "CLM-PROTEIN-SOURCE", "citations": list(citations)}], steps)


def test_a_verbatim_quote_from_a_retrieved_passage_resolves():
    r = report(cite())
    assert (r["total"], r["resolved"], r["unresolved"], r["regulations"]) == (1, 1, [], ["FSS-AC-2018"])


def test_a_paraphrased_quote_does_not_resolve():
    assert report(cite(quote="needs ten percent of the RDA"))["unresolved"]


def test_a_passage_that_was_never_retrieved_does_not_resolve():
    assert report(cite(passage_id="p-other"))["unresolved"]


def test_the_wrong_clause_or_regulation_does_not_resolve():
    assert report(cite(clause_id="Sch-II"))["unresolved"]
    assert report(cite(regulation="FSS-LD-2020"))["unresolved"]


def test_a_trace_without_tool_steps_resolves_nothing():
    assert report(cite(), steps=[{"kind": "llm", "name": "act"}])["resolved"] == 0


def test_injection_report_reads_flags_guardrail_step_and_agent_steps():
    result = {"guardrails": [{"stage": "input", "allowed": False, "flags": ["prompt_injection:label.front_of_pack_text"]}],
              "routing": {"route": "regulatory-review"}}
    steps = [{"kind": "guardrail", "name": "screen_input"}]
    r = demo.injection_report(result, steps, "front_of_pack_text")
    assert r["blocked"] and r["names_field"] and r["guardrail_step"] and r["agent_steps"] == []
    assert demo.injection_report(result, steps + [{"kind": "llm", "name": "classify"}], "front_of_pack_text")["agent_steps"] == ["classify"]


def test_demo_7_passes_in_process(monkeypatch, capsys):
    monkeypatch.setattr(demo, "FAILED", [])
    demo.demo_7(demo.InProcess())
    assert "MISSING" not in capsys.readouterr().out and demo.FAILED == []
