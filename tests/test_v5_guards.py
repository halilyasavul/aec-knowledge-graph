"""Regression tests for the v5 pipeline fixes.

Two classes of defect are covered: a tool result that loses property-set names (the model
then invents them), and an input key that is dropped without an error (the requirement then
disappears while the tool still reports success).
"""
import pytest

import aec_kg.ids.models as m
from aec_kg.main_orchestrator import _truncate_result, _truncate_result_legacy


def _class_result(n_sets=30, n_props=25):
    return {
        "class_code": "IfcWall",
        "class_definition": "x" * 2000,
        "property_sets": {
            f"Pset_Set{i:02d}": {
                "pset_name": f"Set {i}",
                "pset_definition": "y" * 500,
                "properties": [
                    {"code": f"Prop{j:02d}", "name": f"Prop {j}", "definition": "z" * 400,
                     "data_type": "String", "allowed_values": [{"Code": f"V{k}"} for k in range(20)]}
                    for j in range(n_props)
                ],
            }
            for i in range(n_sets)
        },
    }


def test_truncation_keeps_every_property_set_name():
    full = _class_result()
    out = _truncate_result(full, max_chars=5000)
    assert set(out["property_sets"]) == set(full["property_sets"])
    assert out["_truncation"]["dropped_property_sets"] == []


def test_truncation_respects_the_budget_or_reports_why():
    out = _truncate_result(_class_result(), max_chars=20000)
    import json
    assert len(json.dumps(out)) <= 20000 or out["_truncation"]["stages"]


def test_legacy_truncation_still_drops_sets():
    """The v4 behaviour, kept for ablation: sets after the budget hit vanish."""
    full = _class_result()
    out = _truncate_result_legacy(full, max_chars=5000)
    assert out["_truncation"]["dropped_property_sets"], "ablation path should reproduce the old bug"
    assert set(out["property_sets"]) < set(full["property_sets"])


def test_enum_alias_is_accepted():
    assert m.IdsRestriction(enum=["A", "B"]).enumerations == ["A", "B"]


def test_empty_restriction_is_rejected():
    with pytest.raises(Exception):
        m.IdsRestriction(base="xs:string")


def test_unknown_key_is_an_error_not_a_silent_drop():
    with pytest.raises(Exception):
        m.IdsValue(simpleValue="X", surprise=1)


@pytest.mark.parametrize("bad", [".*", "^Niveau", r"[A-Z]{2}", r"REI\s[0-9]{2,3}"])
def test_pattern_in_simplevalue_is_rejected(bad):
    with pytest.raises(Exception):
        m.IdsValue(simpleValue=bad)


@pytest.mark.parametrize("bad", ["REQUIRED", "mandatory", "Fire resistance class according to regulations"])
def test_placeholder_or_prose_value_is_rejected(bad):
    with pytest.raises(Exception):
        m.IdsValue(simpleValue=bad)


@pytest.mark.parametrize("good", ["R 30", "REI 90", "true", "NONE", "FLOOR", "0.3", "00 groundfloor"])
def test_real_values_still_pass(good):
    assert m.IdsValue(simpleValue=good).simpleValue == good


def test_unambiguous_shapes_are_coerced():
    assert m.IdsValue.model_validate("IFCWALL").simpleValue == "IFCWALL"
    assert m.IdsValue.model_validate({"value": "IFCWALL"}).simpleValue == "IFCWALL"
    req = m.Requirements.model_validate([{"propertySet": "Pset_X", "baseName": "Y"}, {"name": "Status"}])
    assert len(req.properties) == 1 and len(req.attributes) == 1


def test_guards_can_be_switched_off_for_ablation():
    m.set_guards(False)
    try:
        assert m.IdsValue(simpleValue=".*").simpleValue == ".*"
    finally:
        m.set_guards(True)
    with pytest.raises(Exception):
        m.IdsValue(simpleValue=".*")
