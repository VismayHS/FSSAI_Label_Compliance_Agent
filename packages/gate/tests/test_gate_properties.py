"""Property-based tests for the gate (extra: hypothesis). Whatever arrives, the boundary holds."""
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from fssai_gate.gate import RequestGate
from fssai_gate.rules import validate

from gate_helpers import valid

json_values = st.recursive(
    st.none() | st.booleans() | st.floats(allow_nan=True, allow_infinity=True) | st.integers() | st.text(max_size=20),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=12), children, max_size=4),
    max_leaves=20)


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(json_values)
def test_any_json_gives_a_decision_never_an_exception(raw):
    d = RequestGate().check(raw, "prop")
    assert d.accepted == (d.request is not None)
    assert d.accepted or (d.errors and d.quarantine_id and all(e.loc and e.message and e.code for e in d.errors))


@settings(max_examples=200)
@given(section=st.sampled_from(["package", "label", "nutrition"]), key=st.text(min_size=1, max_size=10),
       value=json_values)
def test_corrupting_one_field_of_a_valid_request(section, key, value):
    raw = valid()
    raw[section][key] = value
    request, errors = validate(raw)
    assert (request is None) == bool(errors)
    if request is not None:  # if still accepted, the gate's own invariants hold on what it accepted
        n = request.nutrition
        assert (n.added_sugars_g or 0) <= n.total_sugars_g <= n.carbohydrate_g
        assert (n.saturated_fat_g or 0) + (n.trans_fat_g or 0) <= n.total_fat_g


@settings(max_examples=200)
@given(protein=st.floats(0, 30), carbohydrate=st.floats(30, 70), fat=st.floats(0, 25),
       sugar_share=st.floats(0, 1), energy_jitter=st.floats(-0.15, 0.15))
def test_plausible_cereal_panels_are_accepted(protein, carbohydrate, fat, sugar_share, energy_jitter):
    assume(protein + carbohydrate + fat <= 100)  # a real per-100 g panel
    raw = valid()
    computed = 4 * protein + 4 * carbohydrate + 9 * fat
    raw["nutrition"].update(protein_g=protein, carbohydrate_g=carbohydrate, total_fat_g=fat,
                            total_sugars_g=carbohydrate * sugar_share, added_sugars_g=carbohydrate * sugar_share / 2,
                            saturated_fat_g=fat / 4, trans_fat_g=0, energy_kcal=computed * (1 + energy_jitter))
    request, errors = validate(raw)
    assert errors == [], errors
