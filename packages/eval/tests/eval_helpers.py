"""Hand-built runs for the metric tests: a RunResult whose trace holds the retrieved passages, like a real run."""
from __future__ import annotations

from fssai_contracts.conformance import sample_request
from fssai_contracts.schemas import (
    Citation, EvalScenario, Finding, FindingStatus, Passage, Regulation, Route, Routing, RunResult, RunTotals,
    StepRecord, SupportingPassage, utcnow,
)

FIBRE = Passage(passage_id="FSS-AC-2018:Schedule I, item 14~substituted", regulation=Regulation.CLAIMS_2018,
                clause_id="Schedule I, item 14", doc_version="test",
                text="14. Dietary fibre Source Product contains at least 3 g of fibre per 100 g or 1.5 g of fibre per "
                     "100 ml or 1.5 g of fibre per 100kcal High Or Rich The product contains at least 6 g of fibre "
                     "per 100 g or 3 g of fibre per 100 ml or 3 g of fibre per 100 kcal")
ALLERGEN = Passage(passage_id="FSS-LD-2020:5(14)", regulation=Regulation.LABELLING_2020, clause_id="5(14)",
                   doc_version="test", text="(14) Declaration regarding Food allergen: The following foods and "
                   "ingredients which are known to cause allergy shall be declared separately as Contains")
OTHER = Passage(passage_id="FSS-LD-2020:5(9)", regulation=Regulation.LABELLING_2020, clause_id="5(9)",
                doc_version="test", text="(9) Lot/Code/Batch identification.- A batch number or code number or lot "
                "number shall be declared on the label.")


def cite(p: Passage, quote: str) -> Citation:
    return Citation(regulation=p.regulation, clause_id=p.clause_id, passage_id=p.passage_id, quote=quote)


def finding(rid, status, *cites, requirement="", explanation="ok"):
    return Finding(requirement_id=rid, requirement=requirement or rid, status=FindingStatus(status),
                   explanation=explanation, citations=list(cites))


def result(*findings, route=Route.CLEAR_FOR_PRINT, passages=(FIBRE, ALLERGEN, OTHER), complete=True) -> RunResult:
    step = StepRecord(step_index=0, agent="researcher", kind="tool", name="corpus_search", started_at=utcnow(),
                      output={"passages": [p.model_dump(mode="json") for p in passages]})
    return RunResult(run_id="r" * 32, correlation_id="c", complete=complete, routing=Routing(route=route, reason="t"),
                     findings=list(findings), steps=[step], totals=RunTotals(llm_calls=2, tool_calls=1))


def request(fibre=9.0, energy=370, claims=("Source of fibre",)):
    r = sample_request(claims=claims)
    return r.model_copy(update={"nutrition": r.nutrition.model_copy(update={
        "energy_kcal": energy, "other": {"dietary_fibre_g": fibre}})})


def scenario(expected_route=Route.CLEAR_FOR_PRINT, expected=None, supporting=(FIBRE, ALLERGEN), **req) -> EvalScenario:
    return EvalScenario(scenario_id="t-1", description="t", tags=["claim"], request=request(**req),
                        expected_route=expected_route, expected_findings=expected or {},
                        supporting=[SupportingPassage(regulation=p.regulation, clause_id=p.clause_id, quote=p.text[:40])
                                    for p in supporting])
