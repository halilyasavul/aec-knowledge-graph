"""The three dev-set causes from Run 7 (eval/reports/v9/run7_summary.md §4): per-set ifc_type
from the property set templates, partOf/classification/material requirement facets, and the
cardinality annotation for a reference that marks a faithfully required property optional.
"""
import ifcopenshell.ifcopenshell_wrapper as W

from aec_kg.ingest_graph import template_ifc_types


# --------------------------------------------------------------------------- 1. ifc_type gap
def test_template_types_are_per_set():
    t = template_ifc_types()
    # the Run 7 case: bSDD gives "Real" only; the templates disagree by set
    assert t[("Pset_RailingCommon", "Height")] == "IFCPOSITIVELENGTHMEASURE"
    assert t[("Qto_FacilityPartBaseQuantities", "Height")] == "IFCLENGTHMEASURE"
    assert t[("Pset_WallCommon", "FireRating")] == "IFCLABEL"


def test_template_types_are_defined_types_only():
    t = template_ifc_types()
    schema = W.schema_by_name("IFC4X3_ADD2")
    camel = {d.name().upper(): d for d in schema.declarations()}
    assert all(camel[v].as_type_declaration() is not None for v in t.values())
    # a time-series reference property has an entity as its primary type: no dataType for it
    assert ("Pset_SpaceThermalLoadPHistory", "LightingHistory") not in t


# --------------------------------------------------------------------------- 2. new facets
import pytest
from lxml import etree

from aec_kg.ids.models import IdsDocument
from aec_kg.ids.pipeline import generate_ids_from_json
from aec_kg.ids.serializer import serialize_ids
from aec_kg.ids.validator import validate_ids_xml


def _doc(requirements: dict) -> dict:
    return {"info": {"title": "t"},
            "specifications": [{"name": "s", "ifcVersion": "IFC4X3_ADD2",
                                "applicability": {"entity": {"name": {"simpleValue": "IFCSPACE"}}},
                                "requirements": requirements}]}


def _req_children(xml: str) -> list:
    root = etree.fromstring(xml.encode())
    req = root.find(".//{*}requirements")
    return [(etree.QName(c).localname, dict(c.attrib)) for c in req]


@pytest.mark.parametrize("requirements, expect", [
    # Vienna#25: "Alle Räume sind geschossweise zu modellieren"
    ({"partOf": [{"entity": {"name": {"simpleValue": "IfcBuildingStorey"}},
                  "relation": "IfcRelContainedInSpatialStructure"}]},
     [("partOf", {"relation": "IFCRELCONTAINEDINSPATIALSTRUCTURE"})]),
    ({"partOfs": [{"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}}, "cardinality": "prohibited"}]},
     [("partOf", {"cardinality": "prohibited"})]),
    ({"classifications": [{"system": {"simpleValue": "Uniclass 2015"},
                           "value": {"restriction": {"pattern": "SL_.*"}}}]},
     [("classification", {})]),
    ({"classification": [{"system": {"simpleValue": "OmniClass"}, "cardinality": "optional"}]},
     [("classification", {"cardinality": "optional"})]),
    ({"materials": [{"value": {"simpleValue": "Concrete"}}]}, [("material", {})]),
    ({"material": [{}]}, [("material", {})]),
])
def test_new_facets_serialise_xsd_valid(requirements, expect):
    doc = IdsDocument.model_validate(_doc(requirements))
    xml = serialize_ids(doc)
    ok, errors = validate_ids_xml(xml, strict=True)
    assert ok, errors
    assert _req_children(xml) == expect


def test_xsd_order_with_every_facet_kind():
    req = {"materials": [{}], "properties": [{"propertySet": {"simpleValue": "Pset_SpaceCommon"},
                                              "baseName": {"simpleValue": "IsExternal"}}],
           "attributes": [{"name": {"simpleValue": "Name"}}],
           "classifications": [{"system": {"simpleValue": "Uniclass 2015"}}],
           "partOf": [{"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}}}]}
    out = generate_ids_from_json(_doc(req))
    assert out.get("success"), out
    assert [k for k, _ in _req_children(out["ids_xml"])] == ["partOf", "classification", "attribute",
                                                             "property", "material"]
    # classificationType is value-then-system
    xml = serialize_ids(IdsDocument.model_validate(_doc({"classifications": [
        {"system": {"simpleValue": "S"}, "value": {"simpleValue": "V"}}]})))
    cls = etree.fromstring(xml.encode()).find(".//{*}classification")
    assert [etree.QName(c).localname for c in cls] == ["value", "system"]


@pytest.mark.parametrize("part", [
    {"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}}, "relation": "IFCRELCONTAINS"},
    {"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}}, "cardinality": "optional"},
    {"name": {"simpleValue": "IFCBUILDINGSTOREY"}},
])
def test_bad_part_of_is_a_validation_error(part):
    out = generate_ids_from_json(_doc({"partOf": [part]}))
    assert not out.get("success") and out.get("validation_errors"), out


# --------------------------------------------------------------------------- 2b. partOf in the scorer
import ifcopenshell

from eval import witness
from eval.nl_to_ids_testset.extract_testset import facet_target
from eval.score import build_reference, canon, execute, verdicts


def test_part_of_flattens_whole_and_relation():
    xml = serialize_ids(IdsDocument.model_validate(_doc({"partOf": [
        {"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}}, "relation": "IFCRELAGGREGATES"}]})))
    f = facet_target(etree.fromstring(xml.encode()).find(".//{*}partOf"))
    assert f == {"facet": "partOf", "entity": "IFCBUILDINGSTOREY", "relation": "IFCRELAGGREGATES"}
    g = dict(f, relation="IFCRELNESTS")
    assert canon(f) != canon(g)                       # the relation is part of the facet's identity


@pytest.mark.parametrize("relation, part", [
    (None, "IFCSPACE"),                                # any relation: a space aggregated by the storey
    ("IFCRELAGGREGATES", "IFCSPACE"),
    ("IFCRELCONTAINEDINSPATIALSTRUCTURE", "IFCWALL"),
])
def test_witness_builds_part_of(tmp_path, relation, part):
    target = [{"facet": "partOf", "entity": "IFCBUILDINGSTOREY", **({"relation": relation} if relation else {})}]
    item = {"id": "t#1", "applicability": {"entity": part}, "target": target}
    ref = tmp_path / "ref.ids"
    ref.write_bytes(build_reference(item))
    meta = witness.build(item, tmp_path / "w.ifc")
    assert not [u for u in meta["unsupported"] if "partOf" in u], meta["unsupported"]
    ex = execute(ref, ifcopenshell.open(meta["path"]), False)
    v = verdicts(meta["labels"], ex)
    assert v[f"ref:full:{part}"] == "pass" and v["ref:missing:0"] == "fail", v
    assert not witness.verify(meta["labels"], ex, target)


# --------------------------------------------------------------------------- 3. cardinality annotation
from eval.score import adopt_cardinality, load_annotations, relax
from pathlib import Path


def test_cardinality_annotation_leaves_the_comparison():
    ann = load_annotations(Path("eval/annotations/cardinality.jsonl"))
    assert {a["facet_index"] for a in ann["IDS_oma_input.ids#10"]} == {2, 4}
    item = {"id": "IDS_oma_input.ids#10", "target": [
        {"facet": "attribute", "name": "Name"},
        {"facet": "property", "propertySet": "Pset_RampCommon", "baseName": "RequiredSlope"},
        {"facet": "property", "propertySet": "Pset_RampCommon", "baseName": "HandicapAccessible",
         "dataType": "IFCBOOLEAN", "cardinality": "optional"},
        {"facet": "attribute", "name": "PredefinedType"},
        {"facet": "property", "propertySet": "Pset_RampCommon", "baseName": "FireExit",
         "dataType": "IFCBOOLEAN", "cardinality": "optional"}]}
    rel = relax(item, ann["IDS_oma_input.ids#10"])
    assert [bool(f.get("cardinality_free")) for f in rel["target"]] == [False, False, True, False, True]
    # the candidate requires both (no cardinality attribute = required) and has nothing else to say
    cand = {"requirements": [{"facet": "property", "propertySet": "Pset_RampCommon", "baseName": "HandicapAccessible",
                              "dataType": "IFCBOOLEAN"},
                             {"facet": "property", "propertySet": "Pset_RampCommon", "baseName": "FireExit",
                              "dataType": "IFCBOOLEAN", "cardinality": "prohibited"}]}
    out = adopt_cardinality(rel, cand)["target"]
    assert "cardinality" not in out[2] and out[4]["cardinality"] == "prohibited"
    assert canon(out[2]) == canon(cand["requirements"][0])
    # a facet the candidate lacks keeps the reference's cardinality; unannotated facets are untouched
    out = adopt_cardinality(rel, {"requirements": []})["target"]
    assert out[2]["cardinality"] == "optional" and "cardinality" not in out[1]


# --------------------------------------------------------------------------- prompt consistency
from aec_kg.ids.request_checks import RequestContext

USERPSET = {"restriction": {"pattern": "^(?!(Pset_|Qto_)).+"}}


def _prop_doc(pset, name, value=None):
    p = {"propertySet": pset, "baseName": {"simpleValue": name}}
    if value is not None:
        p["value"] = value
    return _doc({"properties": [p]})


@pytest.mark.parametrize("pset, name", [
    (USERPSET, "Slip resistance coefficient"),                  # the request's words, user-defined set
    (USERPSET, "Minimum clear width of the door leaf"),         # five words: a name, not prose
    ({"simpleValue": "ePset_Project"}, "Fire Rating"),          # custom set: spaces allowed
    ({"simpleValue": "Pset_SensorPHistory"}, "Value"),          # a standard name the placeholder guard hit
])
def test_names_in_users_words_are_accepted(pset, name):
    out = generate_ids_from_json(_prop_doc(pset, name), RequestContext(request_text="x"))
    assert out.get("success"), out


def test_standard_set_names_still_need_single_tokens():
    out = generate_ids_from_json(_prop_doc({"simpleValue": "Pset_ColumnCommon"}, "Fire Rating"),
                                 RequestContext(request_text="x"))
    assert out.get("request_errors") and "whitespace" in out["request_errors"][0]


def test_value_guards_still_apply_to_values():
    out = generate_ids_from_json(_prop_doc(USERPSET, "Note", {"simpleValue": "the note must explain the reason here"}))
    assert out.get("validation_errors"), out


# --------------------------------------------------------------------------- regex property sets
import re as _re

from eval.score import _translate_pattern, _xsd_translate

USERPSET_PATTERN = "^(?!(Pset_|Qto_)).+"


def test_xsd_patterns_translate_as_before_and_lookahead_falls_back():
    for p in ("[A-Z]{2}[0-9]+", "REI ?(30|60|90)", r"[\S\s]+[\S]+"):
        assert _translate_pattern(p) == _xsd_translate(p)
    t = _translate_pattern(USERPSET_PATTERN)
    assert _re.fullmatch(t, "Witness 01") and not _re.fullmatch(t, "Pset_WallCommon") and not _re.fullmatch(t, "Qto_X")
    with pytest.raises(_re.error):
        _translate_pattern("(unclosed")


@pytest.mark.parametrize("cand_pset", [f"RESTRICTION(pattern={USERPSET_PATTERN})", "Sidewalk"])
def test_witness_and_executor_handle_a_user_defined_pset(tmp_path, cand_pset):
    target = [{"facet": "property", "propertySet": f"RESTRICTION(pattern={USERPSET_PATTERN})",
               "baseName": "effective width", "dataType": "IFCLENGTHMEASURE",
               "value": "RESTRICTION(minInclusive=2.0)", "cardinality": "required"}]
    item = {"id": "row-x", "applicability": {"entity": "IFCPAVEMENT"}, "target": target}
    ref = tmp_path / "ref.ids"
    ref.write_bytes(build_reference(item))
    cand = {"requirements": [dict(target[0], propertySet=cand_pset)], "applicability": [{"name": "IFCPAVEMENT"}]}
    cand_ids = tmp_path / "cand.ids"
    cand_ids.write_bytes(build_reference({**item, "target": cand["requirements"]}))
    meta = witness.build(item, tmp_path / "w.ifc", candidate=cand)
    model = ifcopenshell.open(meta["path"])
    psets = {ps.Name for ps in model.by_type("IfcPropertySet")}
    assert all(_re.fullmatch(USERPSET_PATTERN, n) or n == cand_pset for n in psets), psets
    rx, cx = execute(ref, model, False), execute(cand_ids, model, False)
    assert not witness.verify(meta["labels"], rx, target)
    rv, cv = verdicts(meta["labels"], rx), verdicts(meta["labels"], cx)
    if cand_pset == "Sidewalk":                       # a named set is stricter than "any user-defined set"
        assert rv["ref:full:IFCPAVEMENT"] == "pass" and cv["ref:full:IFCPAVEMENT"] == "fail"
    else:
        assert rv == cv


def test_witness_builds_for_an_entity_pattern(tmp_path):
    target = [{"facet": "attribute", "name": "Name", "cardinality": "required"}]
    item = {"id": "row-y", "applicability": {"entity": "RESTRICTION(pattern=IFC.*)"}, "target": target}
    ref = tmp_path / "ref.ids"
    ref.write_bytes(build_reference(item))
    meta = witness.build(item, tmp_path / "w.ifc")
    labels = sorted(meta["labels"].values())
    assert "ref:full:IFCWALL" in labels and "ref:full:IFCSLAB" in labels
    assert not [l for l in labels if "decoy:class" in l]          # IFC.* admits every class
    assert not witness.verify(meta["labels"], execute(ref, ifcopenshell.open(meta["path"]), False), target)


# --------------------------------------------------------------------------- stage 2: several specs
from eval.score import parse_candidate, spec_view


def _room_spec(name, area):
    return {"spec_name": name, "applicability": {"entity": "IFCSPACE"},
            "applicability_facets": [{"facet": "entity", "name": "IFCSPACE"},
                                     {"facet": "attribute", "name": "Name", "value": name}],
            "target": [{"facet": "property", "propertySet": f"RESTRICTION(pattern={USERPSET_PATTERN})",
                        "baseName": "Exclusive area", "dataType": "IFCAREAMEASURE",
                        "value": f"RESTRICTION(minInclusive={area})", "cardinality": "required"}]}


def test_multi_spec_reference_witness_and_candidate(tmp_path):
    specs = [_room_spec("Room A", 20), _room_spec("Room B", 30)]
    item = {"id": "row-z", "applicability": {"entity": "IFCSPACE"},
            "target": [f for s in specs for f in s["target"]], "specs": specs}
    assert spec_view(item) is specs
    ref = tmp_path / "ref.ids"
    ref.write_bytes(build_reference(item))
    assert validate_ids_xml(ref.read_text(encoding="utf-8"), strict=True)[0]
    # a candidate that swaps the two bounds: right shape, wrong rooms
    cand_item = {**item, "specs": [_room_spec("Room A", 30), _room_spec("Room B", 20)]}
    cand_path = tmp_path / "cand.ids"
    cand_path.write_bytes(build_reference(cand_item))
    cand = parse_candidate(cand_path)
    assert len(cand["specs"]) == 2 and cand["specs"][1]["applicability_facets"][1]["value"] == "Room B"
    meta = witness.build(item, tmp_path / "w.ifc", candidate=cand)
    labels = set(meta["labels"].values())
    assert {"ref:full:IFCSPACE@0", "ref:full:IFCSPACE@1", "ref:decoy:app0@0", "ref:missing:0@1"} <= labels
    model = ifcopenshell.open(meta["path"])
    rx, cx = execute(ref, model, False), execute(cand_path, model, False)
    assert not witness.verify(meta["labels"], rx, item["target"], meta["spec_targets"])
    rv, cv = verdicts(meta["labels"], rx), verdicts(meta["labels"], cx)
    assert rv["ref:full:IFCSPACE@0"] == "pass" and cv["ref:full:IFCSPACE@0"] == "fail"   # Room A at 25 m2
    assert rv != cv


def test_single_spec_items_keep_the_old_path(tmp_path):
    item = {"id": "d#1", "applicability": {"entity": "IFCWALL"},
            "target": [{"facet": "attribute", "name": "Name"}]}
    assert spec_view(item) is None and spec_view({**item, "specs": [{"applicability_facets": [
        {"facet": "entity", "name": "IFCWALL"}], "target": item["target"]}]}) is None
    meta = witness.build(item, tmp_path / "w.ifc")
    assert meta["spec_targets"] is None and not any("@" in l for l in meta["labels"].values())


# --------------------------------------------------------------------------- Run 10: applicability facets
def test_applicability_selects_by_attribute_and_property():
    doc = {"info": {"title": "t"}, "specifications": [
        {"name": "Room A", "ifcVersion": "IFC4X3_ADD2",
         "applicability": {"entity": {"name": {"simpleValue": "IFCSPACE"}},
                           "attributes": [{"name": {"simpleValue": "Name"}, "value": {"simpleValue": "Room A"},
                                           "cardinality": "required"}]},
         "requirements": {"properties": [{"propertySet": USERPSET, "baseName": {"simpleValue": "Exclusive area"},
                                          "dataType": "IFCAREAMEASURE", "value": {"restriction": {"minInclusive": "20"}}}]}},
        {"name": "flat slabs", "ifcVersion": "IFC4X3_ADD2",
         "applicability": {"entity": {"name": {"simpleValue": "IFCSLAB"}},
                           "properties": [{"propertySet": USERPSET, "baseName": {"simpleValue": "Slope"},
                                           "value": {"restriction": {"maxExclusive": "0.05"}}}],
                           "partOf": [{"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}}}]},
         "requirements": {"properties": [{"propertySet": USERPSET, "baseName": {"simpleValue": "Slip resistance"}}]}}]}
    out = generate_ids_from_json(doc)
    assert out.get("success"), out
    root = etree.fromstring(out["ids_xml"].encode())
    apps = root.findall(".//{*}applicability")
    assert [etree.QName(c).localname for c in apps[0]] == ["entity", "attribute"]
    assert [etree.QName(c).localname for c in apps[1]] == ["entity", "partOf", "property"]
    assert all("cardinality" not in c.attrib for a in apps for c in a)     # the XSD has none here


# --------------------------------------------------------------------------- audit: serializer defaults
import os
import shutil
import subprocess

from aec_kg.ids.serializer import xsd_base


def _app_and_value(doc: dict) -> tuple:
    root = etree.fromstring(serialize_ids(IdsDocument.model_validate(doc)).encode())
    app = root.find(".//{*}applicability")
    r = root.find(".//{*}requirements//{*}value/{*}restriction")       # the value's, not the pset's
    return dict(app.attrib), (r.get("base") if r is not None else None)


@pytest.mark.parametrize("app_extra, expect", [
    ({}, {"minOccurs": "0", "maxOccurs": "unbounded"}),                     # unstated: optional, not [1..1]
    ({"minOccurs": 1}, {"minOccurs": "1", "maxOccurs": "unbounded"}),       # required
    ({"minOccurs": 0, "maxOccurs": "0"}, {"minOccurs": "0", "maxOccurs": "0"}),   # prohibited
])
def test_applicability_occurs(app_extra, expect):
    doc = _doc({"attributes": [{"name": {"simpleValue": "Name"}}]})
    doc["specifications"][0]["applicability"].update(app_extra)
    assert _app_and_value(doc)[0] == expect


@pytest.mark.parametrize("dtype, value, base", [
    ("IFCLENGTHMEASURE", {"minInclusive": "2.0"}, "xs:double"),
    ("IFCCOUNTMEASURE", {"enumerations": ["1", "2"]}, "xs:integer"),     # INTEGER in IFC 4.3
    ("IFCLABEL", {"enumerations": ["Tile", "Carpet"]}, "xs:string"),
    ("IFCDATE", {"minInclusive": "2029-03-31"}, "xs:date"),
    ("IFCBOOLEAN", {"enumerations": ["true", "false"]}, "xs:boolean"),
    (None, {"maxInclusive": "0.02"}, "xs:double"),                        # bounds without a dataType
    (None, {"pattern": "[A-Z]+"}, "xs:string"),
    ("IFCLENGTHMEASURE", {"base": "xs:decimal", "minInclusive": "1"}, "xs:decimal"),   # a stated base wins
])
def test_restriction_base_follows_the_datatype(dtype, value, base):
    p = {"propertySet": USERPSET, "baseName": {"simpleValue": "x"}, "value": {"restriction": value}}
    if dtype:
        p["dataType"] = dtype
    assert _app_and_value(_doc({"properties": [p]}))[1] == base


_IDS_TOOL = shutil.which("ids-tool") or os.path.expandvars(r"$USERPROFILE\.dotnet\tools\ids-tool.exe")
needs_ids_tool = pytest.mark.skipif(not os.path.exists(_IDS_TOOL), reason="buildingSMART ids-tool not installed")


@needs_ids_tool
def test_xsd_base_is_what_the_official_audit_expects(tmp_path):
    """Every IFC 4.3 defined type, with the base xsd_base gives it: ids-tool reports no error 303."""
    schema = W.schema_by_name("IFC4X3_ADD2")
    types = sorted(d.name().upper() for d in schema.declarations() if isinstance(d, W.type_declaration))
    specs = [{"name": t, "ifcVersion": "IFC4X3_ADD2",
              "applicability": {"entity": {"name": {"simpleValue": "IFCWALL"}}},
              "requirements": {"properties": [{"propertySet": {"simpleValue": "P"}, "baseName": {"simpleValue": "B"},
                                               "dataType": t, "value": {"restriction": {"pattern": ".+"}}}]}}
             for t in types]
    f = tmp_path / "all_types.ids"
    f.write_text(serialize_ids(IdsDocument.model_validate({"info": {"title": "t"}, "specifications": specs})),
                 encoding="utf-8")
    out = subprocess.run([_IDS_TOOL, "audit", str(f)], capture_output=True, text=True, encoding="utf-8").stdout
    assert "Error 303" not in out, [l for l in out.splitlines() if "Error 303" in l][:5]


@needs_ids_tool
def test_a_typical_document_passes_the_official_audit(tmp_path):
    p = [{"propertySet": USERPSET, "baseName": {"simpleValue": "effective width"}, "dataType": "IFCLENGTHMEASURE",
          "value": {"restriction": {"minInclusive": "2.0"}}},
         {"propertySet": {"simpleValue": "Pset_WallCommon"}, "baseName": {"simpleValue": "FireRating"},
          "dataType": "IFCLABEL", "value": {"restriction": {"enumerations": ["REI 30", "REI 60"]}}}]
    doc = _doc({"properties": p})
    doc["specifications"][0]["applicability"]["entity"]["name"]["simpleValue"] = "IFCWALL"   # Pset_WallCommon's class
    f = tmp_path / "doc.ids"
    f.write_text(serialize_ids(IdsDocument.model_validate(doc)), encoding="utf-8")
    r = subprocess.run([_IDS_TOOL, "audit", str(f)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-800:]
