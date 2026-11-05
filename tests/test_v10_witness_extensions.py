"""v10b witness-builder extensions (eval/witness.py, EXTENSIONS switch).

Off (the default) the builder must behave as before; on, it builds the usBridge facet shapes it
could not: a single required enumeration value, properties on type objects, a type object's
user-defined predefined type, and a partOf whole given as a pattern.
"""
import pytest

from eval import witness


@pytest.fixture(params=[False, True])
def ext(request, monkeypatch):
    monkeypatch.setattr(witness, "EXTENSIONS", request.param)
    return request.param


def test_single_enumeration_value(ext):
    b = witness.Builder("t")
    el = b.element("IFCBRIDGEPART", "x", "PIER")
    assert witness.apply_facet(b, el, {"facet": "attribute", "name": "CompositionType", "value": "ELEMENT"})
    assert el.CompositionType == ("ELEMENT" if ext else "COMPLEX")      # off: the old first-member pick


def test_properties_on_a_type_object(ext):
    b = witness.Builder("t")
    el = b.element("IFCREINFORCINGBARTYPE", "x", None)
    witness.apply_facet(b, el, {"facet": "property", "propertySet": "usBrPset_Reinforcing",
                                "baseName": "PlacementMethod", "dataType": "IFCLABEL"})
    rels = b.f.by_type("IfcRelDefinesByProperties")
    if ext:
        assert not rels and [p.Name for p in el.HasPropertySets] == ["usBrPset_Reinforcing"]
    else:
        assert len(rels) == 1 and not el.HasPropertySets


def test_user_defined_type_of_a_type_object(ext):
    b = witness.Builder("t")
    el = b.element("IFCREINFORCINGBARTYPE", "x", "DOWEL")
    assert el.PredefinedType == "USERDEFINED"
    assert (el.ElementType == "DOWEL") if ext else (el.ElementType is None)


def test_partof_any_whole(ext):
    b = witness.Builder("t")
    el = b.element("IFCELEMENTASSEMBLY", "x", None)
    ok = witness.apply_facet(b, el, {"facet": "partOf", "entity": "RESTRICTION(pattern=.*)",
                                     "relation": "IFCRELAGGREGATES", "cardinality": "required"})
    if ext:
        assert ok and b.f.by_type("IfcRelAggregates")[0].RelatingObject.is_a("IfcElementAssembly")
    else:
        assert not ok and not b.f.by_type("IfcRelAggregates")


def test_a_whole_class_spec_adds_its_requirements(ext):
    item = {"id": "t", "applicability": {"entity": "IFCREINFORCINGBARTYPE"}, "target": [],
            "specs": [{"applicability_facets": [{"facet": "entity", "name": "IFCREINFORCINGBARTYPE"}],
                       "target": [{"facet": "attribute", "name": "Name", "cardinality": "required"}]},
                      {"applicability_facets": [{"facet": "entity", "name": "IFCREINFORCINGBARTYPE", "predefinedType": "DOWEL"}],
                       "target": [{"facet": "attribute", "name": "Description", "cardinality": "required"}]}]}
    specs = witness._ref_specs(item)
    dowel = next(s for s in specs if s["app"].get("predefinedType") == "DOWEL")
    names = [f["name"] for f in dowel["target"]]
    assert names == (["Description", "Name"] if ext else ["Description"])


def test_a_covering_spec_does_not_duplicate_a_facet(ext):
    req = {"facet": "property", "propertySet": "P", "baseName": "X", "cardinality": "required"}
    opt = {**req, "cardinality": "optional"}
    item = {"id": "t", "applicability": {"entity": "IFCWALL"}, "target": [],
            "specs": [{"applicability_facets": [{"facet": "entity", "name": "IFCWALL"}], "target": [opt]},
                      {"applicability_facets": [{"facet": "entity", "name": "IFCWALL", "predefinedType": "BACKWALL"}],
                       "target": [req]}]}
    typed = next(s for s in witness._ref_specs(item) if s["app"].get("predefinedType"))
    assert typed["target"] == [req]


def test_off_by_default():
    import importlib
    assert importlib.reload(witness).EXTENSIONS is False
