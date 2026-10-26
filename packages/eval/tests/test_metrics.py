"""The L3 metrics on hand-built runs: each definition in fssai_eval.metrics, one behaviour per test."""
from fssai_contracts.schemas import FindingStatus, Route
from fssai_eval.judges import ReferenceJudge
from fssai_eval.metrics import aggregate, id_tokens, match_finding, score_response

from eval_helpers import ALLERGEN, FIBRE, OTHER, cite, finding, request, result, scenario

J = ReferenceJudge()
FIBRE_Q = "Product contains at least 3 g of fibre per 100 g"
ALLERGEN_Q = "shall be declared separately as Contains"


def fibre_met(quote=FIBRE_Q):
    return finding("CLM-FIBRE-SOURCE", "met", cite(FIBRE, quote), requirement="Condition for claim 'Source of fibre'")


def test_grounded_and_faithful_response():
    row = score_response(result(fibre_met(), finding("LBL-ALLERGEN", "met", cite(ALLERGEN, ALLERGEN_Q))),
                         request(), J, scenario())
    assert row.groundedness == 1.0 and row.faithfulness == 1.0 and row.hallucinated is False
    assert row.citation_resolution == 1.0


def test_paraphrased_citation_is_ungrounded_and_a_hallucination():
    row = score_response(result(fibre_met("fibre must be at least three grams")), request(), J, scenario())
    assert row.groundedness == 0.0 and row.hallucinated is True and row.citation_resolution == 0.0
    assert row.statements[0].faithful is False and row.statements[0].faithful_by == "citation"


def test_citation_to_a_passage_never_retrieved_is_ungrounded():
    row = score_response(result(fibre_met(), passages=(ALLERGEN,)), request(), J, scenario())
    assert row.groundedness == 0.0 and row.hallucinated is True


def test_grounded_but_wrong_conclusion_is_unfaithful():
    """Groundedness and faithfulness differ: the quote is real, the status does not follow from it."""
    row = score_response(result(fibre_met()), request(fibre=1.0), J, scenario())
    s = row.statements[0]
    assert s.groundedness == 1.0 and s.faithful is False and s.faithful_by == "numeric:mismatch"
    assert row.groundedness == 1.0 and row.faithfulness == 0.0 and row.hallucinated is True


def test_decisive_statement_without_citation_is_ungrounded():
    row = score_response(result(finding("LBL-BATCH", "unmet")), request(), J, scenario())
    assert row.groundedness == 0.0 and row.hallucinated is True


def test_undetermined_without_citation_makes_no_statement():
    row = score_response(result(finding("CLM-PROTEIN-SOURCE", "cannot_determine"), route=Route.REGULATORY_REVIEW),
                         request(), J, scenario())
    assert row.statements == [] and row.hallucinated is None and row.groundedness is None


def test_context_relevance_against_gold_clauses():
    row = score_response(result(fibre_met()), request(), J, scenario())   # 2 of 3 retrieved passages are gold
    assert row.context_relevance == round(2 / 3, 4)


def test_live_runs_have_no_offline_relevance():
    assert score_response(result(fibre_met()), request(), J, None).context_relevance is None


def test_expected_findings_match_by_fuzzy_id():
    sc = scenario(expected={"CLM-FIBER-SOURCE": FindingStatus.MET, "LBL-VEG-MARK": FindingStatus.MET})
    row = score_response(result(fibre_met()), request(), J, sc)
    assert row.expected_findings["CLM-FIBER-SOURCE"]["correct"]
    assert row.expected_findings["LBL-VEG-MARK"]["got"] is None


def test_id_matching():
    from eval_helpers import finding as f
    fs = [f("LBL-VEG-LOGO", "met"), f("LBL-LICENSE", "met"), f("CLM-SUGAR-LOW", "unmet")]
    assert match_finding("LBL-VEG-MARK", fs).requirement_id == "LBL-VEG-LOGO"
    assert match_finding("LBL-FSSAI-LICENCE", fs).requirement_id == "LBL-LICENSE"
    assert match_finding("CLM-SUGARS-LOW", fs).requirement_id == "CLM-SUGAR-LOW"
    assert match_finding("LBL-ALLERGEN", fs) is None
    assert match_finding("CLM-VEG-MARK", fs) is None, "LBL and CLM ids never match each other"
    assert id_tokens("LBL-NUTRITIONAL-INFORMATION") == {"LBL", "NUTRITION"}


def test_aggregate_counts_hallucination_per_response():
    good = score_response(result(fibre_met()), request(), J, scenario())
    # one response with one bad statement out of three is one hallucinated response, not 1/3 of one
    mixed = score_response(result(fibre_met(), finding("LBL-ALLERGEN", "met", cite(ALLERGEN, ALLERGEN_Q)),
                                  finding("LBL-BATCH", "met", cite(OTHER, "not in the passage at all"))),
                           request(), J, scenario())
    a = aggregate([good, mixed])
    assert a["hallucination_rate"] == 0.5 and a["responses_with_statements"] == 2


def test_aggregate_route_metrics():
    cleared_wrongly = score_response(result(fibre_met()), request(), J, scenario(expected_route=Route.REVISE_AND_RECHECK))
    escalated = score_response(result(route=Route.REGULATORY_REVIEW), request(), J,
                               scenario(expected_route=Route.REGULATORY_REVIEW))
    a = aggregate([cleared_wrongly, escalated])
    assert a["route_accuracy"] == 0.5 and a["escalation_recall"] == 1.0 and a["unsafe_clear_rate"] == 1.0
