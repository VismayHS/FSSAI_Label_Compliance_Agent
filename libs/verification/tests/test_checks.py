"""The deterministic checks: citation resolution and re-reading numeric claim conditions from passage text."""
import pytest

from fssai_contracts.schemas import FindingStatus
from fssai_verification.checks import claim_kind, nutrient_of, numeric_check, read_condition, resolve_citation

from verification_helpers import SCHED, cite, finding, request

MET, UNMET = FindingStatus.MET, FindingStatus.UNMET
PASSAGES = {p.passage_id: p for p in SCHED.values()}


# ---------------------------------------------------------------- resolve_citation

def test_verbatim_quote_resolves():
    p = SCHED["allergen"]
    assert resolve_citation(cite(p, "shall be declared separately as Contains"), PASSAGES).resolved


def test_whitespace_and_curly_quotes_are_normalised():
    p = SCHED["allergen"]
    assert resolve_citation(cite(p, "known  to cause\nallergy shall be declared"), PASSAGES).resolved


def test_paraphrase_does_not_resolve():
    r = resolve_citation(cite(SCHED["allergen"], "allergens must be listed separately"), PASSAGES)
    assert (r.resolved, r.problem) == (False, "not_verbatim")


def test_unretrieved_passage_does_not_resolve_even_with_its_real_text():
    p = SCHED["allergen"]
    r = resolve_citation(cite(p), {})
    assert (r.resolved, r.problem) == (False, "not_retrieved")


def test_empty_quote_does_not_resolve():
    assert resolve_citation(cite(SCHED["allergen"], "  "), PASSAGES).problem == "empty_quote"


def test_case_is_not_folded():
    """A quote must be the passage's own words; changing case is editing the regulation."""
    assert not resolve_citation(cite(SCHED["allergen"], "SHALL BE DECLARED SEPARATELY"), PASSAGES).resolved


# ---------------------------------------------------------------- reading conditions from the real rows

def test_fibre_source_condition_has_three_bases():
    c = read_condition(SCHED["fibre"].text, "source")
    assert c.thresholds == {"100 g": (3.0, "g"), "100 ml": (1.5, "g"), "100 kcal": (1.5, "g")}
    assert not c.relative


def test_fibre_high_condition_is_its_own_segment():
    assert read_condition(SCHED["fibre"].text, "high").thresholds["100 g"] == (6.0, "g")


def test_sugars_low_and_free():
    assert read_condition(SCHED["sugars"].text, "low").thresholds["100 g"] == (6.0, "g")
    free = read_condition(SCHED["sugars"].text, "free").thresholds
    assert free["100 g"] == (0.5, "g") and free["100 ml"] == (0.5, "g")  # "per 100 g for solids or 100 ml"


def test_sodium_low_is_not_confused_with_very_low():
    assert read_condition(SCHED["sodium"].text, "low").thresholds["100 g"] == (0.12, "g")


def test_trans_fat_free_is_strict():
    c = read_condition(SCHED["trans"].text, "free")
    assert c.strict and c.thresholds["100 g"] == (0.2, "g")


def test_protein_condition_is_relative_to_rda():
    c = read_condition(SCHED["protein"].text, "source")
    assert c.relative


def test_passage_without_the_claim_word_gives_no_condition():
    assert read_condition(SCHED["allergen"].text, "source") is None


@pytest.mark.parametrize("text,kind", [("Source of protein", "source"), ("High in fibre", "high"),
                                       ("Protein rich", "high"), ("Low sugar", "low"), ("Trans fat free", "free"),
                                       ("Contains protein", "source"), ("Tasty and crunchy", None)])
def test_claim_kind(text, kind):
    assert claim_kind(text) == kind


def test_specific_nutrient_wins_over_fat():
    assert nutrient_of("Low saturated fat")[1] == "saturated_fat_g"
    assert nutrient_of("Trans fat free")[1] == "trans_fat_g"
    assert nutrient_of("Low fat")[1] == "total_fat_g"


# ---------------------------------------------------------------- numeric_check

def _num(claim, status, passage, tolerance=20.0, **nutrition):
    f = finding("CLM-X", status, cite(passage), requirement=f"Condition for claim '{claim}'")
    return numeric_check(f, claim, request(claims=(claim,), **nutrition), [passage], tolerance)


def test_fibre_source_met_when_clearly_above():
    r = _num("Source of fibre", MET, SCHED["fibre"], energy_kcal=380, other={"dietary_fibre_g": 9.0})
    assert r.outcome == "consistent" and r.expected == MET


def test_finding_says_met_but_number_says_unmet():
    r = _num("Source of fibre", MET, SCHED["fibre"], energy_kcal=380, other={"dietary_fibre_g": 1.0})
    assert r.outcome == "mismatch" and r.expected == UNMET


def test_finding_says_unmet_but_number_says_met():
    r = _num("Low sugar", UNMET, SCHED["sugars"], total_sugars_g=2.0)
    assert r.outcome == "mismatch" and r.expected == MET


def test_tolerance_on_the_declared_value_spanning_the_threshold_is_borderline():
    # 5.5 g declared, +/-20% -> 4.4..6.6 g, which spans the 6 g condition
    assert _num("Low sugar", MET, SCHED["sugars"], total_sugars_g=5.5).outcome == "borderline"
    # 4.5 g declared -> 3.6..5.4 g, clearly under 6 g
    assert _num("Low sugar", MET, SCHED["sugars"], total_sugars_g=4.5).outcome == "consistent"


def test_value_exactly_at_the_threshold_is_borderline():
    assert _num("Source of fibre", MET, SCHED["fibre"], energy_kcal=150, other={"dietary_fibre_g": 3.0}).outcome == "borderline"


def test_tolerance_can_be_turned_off():
    assert _num("Low sugar", MET, SCHED["sugars"], tolerance=0, total_sugars_g=5.5).outcome == "consistent"


def test_sodium_mg_is_converted_to_the_conditions_grams():
    assert _num("Low sodium", MET, SCHED["sodium"], sodium_mg=50).outcome == "consistent"   # 0.05 g <= 0.12 g
    assert _num("Low sodium", MET, SCHED["sodium"], sodium_mg=400).outcome == "mismatch"    # 0.4 g > 0.12 g


def test_bases_that_disagree_escalate():
    # 4 g fibre per 100 g meets 3 g/100 g; at 400 kcal per 100 g that is 1.0 g per 100 kcal, below 1.5
    r = _num("Source of fibre", MET, SCHED["fibre"], energy_kcal=400, other={"dietary_fibre_g": 4.0})
    assert r.outcome == "bases_disagree"


def test_rda_condition_needs_a_reference_value():
    r = _num("Source of protein", MET, SCHED["protein"], protein_g=14)
    assert r.outcome == "needs_reference" and r.expected is None


def test_claimed_nutrient_not_declared():
    assert _num("Source of fibre", MET, SCHED["fibre"]).outcome == "missing_value"


def test_cannot_determine_findings_are_not_rechecked():
    assert not _num("Source of protein", FindingStatus.CANNOT_DETERMINE, SCHED["protein"]).applicable


# ---------------------------------------------------------------- found in review

def test_very_low_is_its_own_claim_kind():
    """'Very low sodium' must be checked against Very low (0.04 g), not Low (0.12 g)."""
    assert claim_kind("Very low sodium") == "very low"
    assert read_condition(SCHED["sodium"].text, "very low").thresholds["100 g"] == (0.04, "g")
    r = _num("Very low sodium", MET, SCHED["sodium"], sodium_mg=100)  # 0.1 g: Low yes, Very low no
    assert r.outcome == "mismatch" and r.expected == UNMET


def test_added_sugar_claims_are_not_schedule_i_numbers():
    """Non-addition claims are FSS-AC-2018 6(1) conditions, not the 'Sugar free' row."""
    assert claim_kind("Without added sugar") is None
    assert claim_kind("No added sugar") is None
    assert not _num("Without added sugar", MET, SCHED["sugars"], total_sugars_g=12).applicable


def test_conditions_are_read_only_from_the_claims_regulation():
    """A labelling passage that happens to say 'free ... per 100 g' is not a claim condition."""
    from verification_helpers import passage
    from fssai_contracts.schemas import Regulation
    ld = passage("FSS-LD-2020:9(9)", "Free The product contains not more than 0.5 g of sugars per 100 g",
                 reg=Regulation.LABELLING_2020)
    assert not _num("Sugar free", MET, ld, total_sugars_g=12).applicable


def test_bases_disagree_detail_names_each_basis():
    r = _num("Source of fibre", MET, SCHED["fibre"], energy_kcal=400, other={"dietary_fibre_g": 4.0})
    assert "per 100 g: met" in r.detail and "per 100 kcal: not met" in r.detail
