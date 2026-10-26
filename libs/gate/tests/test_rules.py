"""The data contract's rules (docs/data-contract.md), one test per rule id where it has one."""
import pytest

from fssai_gate.rules import validate

from gate_helpers import DELETE, valid, with_


def codes(raw):
    request, errors = validate(raw)
    assert (request is None) == bool(errors), "a request is returned exactly when there are no errors"
    return {(e.loc, e.code) for e in errors}


def test_valid_request_passes():
    request, errors = validate(valid())
    assert errors == [] and request.declared_category == "breakfast-cereals"


def test_minimal_request_passes():
    raw = valid()
    raw["label"] = {"product_name": "Plain oats"}
    raw["nutrition"] = {"basis": "per_100g", "energy_kcal": 380, "protein_g": 12, "carbohydrate_g": 66,
                        "total_sugars_g": 1, "total_fat_g": 7}
    raw["package"] = {"net_quantity": 1, "net_quantity_unit": "kg", "principal_display_panel_cm2": 300}
    assert validate(raw)[1] == []


# ---------------------------------------------------------------- schema and type

def test_missing_and_wrong_type_are_both_reported():
    raw = with_("nutrition.protein_g", "lots", with_("label.product_name", DELETE))
    got = codes(raw)
    assert ("label.product_name", "missing") in got and ("nutrition.protein_g", "type") in got


def test_enum_values():
    assert ("nutrition.basis", "enum") in codes(with_("nutrition.basis", "per_serving"))
    assert ("label.veg_status", "enum") in codes(with_("label.veg_status", "vegan"))
    assert ("package.pack_type", "enum") in codes(with_("package.pack_type", "crate"))


def test_misspelt_field_is_rejected_not_dropped():
    raw = with_("nutrition.protien_g", 12)
    assert ("nutrition.protien_g", "unknown_field") in codes(raw)
    assert ("surprise", "unknown_field") in codes({**valid(), "surprise": 1})


@pytest.mark.parametrize("body", [[], "text", 3, None])
def test_non_object_body(body):
    assert codes(body) == {("body", "type")}


def test_wrapped_unparseable_body_from_the_api():
    assert codes({"_unparseable_body": "{not json"}) == {("body", "json_invalid")}


# ---------------------------------------------------------------- version, ranges, lengths, formats, category

@pytest.mark.parametrize("version,ok", [("1.0", True), ("1.3", True), ("2.0", False), ("one", False), ("1", False)])
def test_schema_version(version, ok):
    assert (("schema_version", "version") not in codes(with_("schema_version", version))) == ok


@pytest.mark.parametrize("loc,value", [
    ("nutrition.protein_g", -1), ("nutrition.protein_g", 101), ("nutrition.energy_kcal", 901),
    ("nutrition.sodium_mg", 40_001), ("package.principal_display_panel_cm2", 0),
    ("nutrition.serving_size", 0), ("nutrition.saturated_fat_g", -0.1),
])
def test_ranges(loc, value):
    assert (loc, "range") in codes(with_(loc, value))


def test_net_quantity_range_depends_on_its_unit():
    assert ("package.net_quantity", "range") in codes(with_("package.net_quantity", 0))
    kg = with_("package.net_quantity_unit", "kg", with_("package.net_quantity", 500))
    assert ("package.net_quantity", "range") in codes(kg)  # 500 kg: almost certainly meant grams


def test_range_errors_are_found_even_when_another_field_has_a_type_error():
    raw = with_("nutrition.protein_g", 150, with_("nutrition.total_fat_g", "six"))
    got = codes(raw)
    assert ("nutrition.protein_g", "range") in got and ("nutrition.total_fat_g", "type") in got


def test_other_keys_carry_their_unit():
    assert ("nutrition.other.fibre", "format") in codes(with_("nutrition.other", {"fibre": 3}))
    assert ("nutrition.other.dietary_fibre_g", "range") in codes(with_("nutrition.other", {"dietary_fibre_g": 120}))


def test_lengths():
    assert ("label.product_name", "length") in codes(with_("label.product_name", "   "))
    assert ("label.ingredients", "length") in codes(with_("label.ingredients", "x" * 4001))
    assert ("label.claims.0", "length") in codes(with_("label.claims", [" "]))
    assert ("label.claims", "length") in codes(with_("label.claims", [f"claim {i}" for i in range(21)]))


@pytest.mark.parametrize("lic,ok", [("10012345678901", True), ("100 1234 5678 901", True), ("1234", False),
                                    ("ABCDEFGHIJKLMN", False)])
def test_licence_number_format(lic, ok):
    assert (("label.fssai_licence_number", "format") not in codes(with_("label.fssai_licence_number", lic))) == ok


def test_missing_licence_is_a_finding_not_a_reject():
    assert codes(with_("label.fssai_licence_number", DELETE)) == set()


@pytest.mark.parametrize("category,ok", [("breakfast-cereals", True), ("alcoholic-beverage", True),
                                         ("other", True), ("Breakfast Cereals", False), ("x", False), ("", False)])
def test_category_format_but_not_coverage(category, ok):
    """Out-of-corpus categories are accepted and escalate downstream (F7); only malformed ids are rejected."""
    assert (("declared_category", "category") not in codes(with_("declared_category", category))) == ok


# ---------------------------------------------------------------- cross-field rules

def test_xf01_per_100ml_needs_a_volume():
    assert ("nutrition.basis", "XF-01") in codes(with_("nutrition.serving_unit", "ml", with_("nutrition.basis", "per_100ml")))


def test_xf02_serving_size_and_unit_together():
    assert ("nutrition.serving_unit", "XF-02") in codes(with_("nutrition.serving_unit", DELETE))
    assert ("nutrition.serving_size", "XF-02") in codes(with_("nutrition.serving_size", DELETE))


def test_xf03_serving_unit_matches_basis():
    assert ("nutrition.serving_unit", "XF-03") in codes(with_("nutrition.serving_unit", "ml"))


def test_xf04_added_sugars_at_most_total():
    assert ("nutrition.added_sugars_g", "XF-04") in codes(with_("nutrition.added_sugars_g", 10))


def test_xf05_sugars_at_most_carbohydrate():
    raw = with_("nutrition.total_sugars_g", 80, with_("nutrition.added_sugars_g", 1))
    assert ("nutrition.total_sugars_g", "XF-05") in codes(raw)


def test_xf06_fat_parts_at_most_total():
    assert ("nutrition.saturated_fat_g", "XF-06") in codes(with_("nutrition.trans_fat_g", 5.5))


def test_xf07_mass_balance():
    raw = valid()
    raw["nutrition"].update(protein_g=40, carbohydrate_g=60, total_fat_g=10, energy_kcal=490)
    assert ("nutrition", "XF-07") in codes(raw)


@pytest.mark.parametrize("energy,ok", [(382, True), (310, True), (455, True), (300, False), (470, False)])
def test_xf08_energy_consistent_with_4_4_9(energy, ok):
    # computed 382 kcal; 20% tolerance (FSS-LD-2020 5(3)(d)) = +/-76.4
    assert (("nutrition.energy_kcal", "XF-08") not in codes(with_("nutrition.energy_kcal", energy))) == ok


def test_xf08_floor_for_small_values():
    raw = valid()
    raw["nutrition"].update(energy_kcal=8, protein_g=0, carbohydrate_g=0.5, total_sugars_g=0.2, added_sugars_g=0,
                            total_fat_g=0.1, saturated_fat_g=0)
    raw["label"]["claims"] = []
    assert codes(raw) == set()  # computed 2.9 kcal, within the 10 kcal floor


def test_xf09_panel_within_surface():
    assert ("package.principal_display_panel_cm2", "XF-09") in codes(with_("package.total_surface_area_cm2", 100))


@pytest.mark.parametrize("claim,loc", [
    ("High in fibre", "nutrition.other.dietary_fibre_g"), ("Low sodium", "nutrition.sodium_mg"),
    ("Low salt", "nutrition.sodium_mg"), ("Low saturated fat", "nutrition.saturated_fat_g"),
    ("Trans fat free", "nutrition.trans_fat_g"), ("No added sugar", "nutrition.added_sugars_g"),
])
def test_xf10_claimed_nutrient_is_declared(claim, loc):
    raw = valid()
    raw["label"]["claims"] = [claim]
    raw["nutrition"].pop(loc.split(".")[1], None)
    raw["nutrition"]["other"] = {}
    if loc == "nutrition.saturated_fat_g":
        raw["nutrition"].pop("trans_fat_g")
    assert (loc, "XF-10") in codes(raw)


def test_xf10_micronutrient_claims():
    raw = with_("label.claims", ["Source of iron"])
    assert ("label.claims.0", "XF-10") in codes(raw)
    raw["nutrition"]["other"]["iron_mg"] = 4
    assert ("label.claims.0", "XF-10") not in codes(raw)


def test_protein_claim_needs_nothing_extra():
    assert codes(with_("label.claims", ["Source of protein"])) == set()


# ---------------------------------------------------------------- all errors at once

def test_every_error_is_collected_not_just_the_first():
    raw = valid()
    raw["nutrition"].update(added_sugars_g=20, trans_fat_g=9, energy_kcal=50)
    raw["label"]["fssai_licence_number"] = "12"
    raw["package"]["pack_type"] = "crate"
    got = {c for _, c in codes(raw)}
    assert {"XF-04", "XF-06", "XF-08", "format", "enum"} <= got


# ---------------------------------------------------------------- found in review: values JSON allows but numbers must not be

@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(value):
    """json.loads accepts NaN/Infinity, and every comparison with NaN is false, so no range rule would catch it."""
    assert ("nutrition.protein_g", "range") in codes(with_("nutrition.protein_g", value))
    assert ("nutrition.other.dietary_fibre_g", "range") in codes(with_("nutrition.other", {"dietary_fibre_g": value}))


def test_numeric_strings_are_not_coerced():
    """The published schema says number; the gate must agree with it."""
    assert ("nutrition.protein_g", "type") in codes(with_("nutrition.protein_g", "12"))
    assert ("package.net_quantity", "type") in codes(with_("package.net_quantity", "500"))


def test_integers_are_fine_for_number_fields():
    assert codes(with_("nutrition.protein_g", 10)) == set()
