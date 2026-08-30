"""Unit tests for the EXPRESS schema parser.

Uses a small inline EXPRESS snippet mirroring the layout of the real
IFC4X3_ADD2 file (tab-indented attributes, space-indented section keywords),
so no buildingSMART data files are required.
"""

from aec_kg.express_parser import parse_express

SAMPLE = (
    "SCHEMA IFC_TEST;\n"
    "\n"
    "TYPE IfcLabel = STRING(255);\n"
    "END_TYPE;\n"
    "\n"
    "TYPE IfcWallTypeEnum = ENUMERATION OF\n"
    "\t(MOVABLE\n"
    "\t,SOLIDWALL\n"
    "\t,USERDEFINED);\n"
    "END_TYPE;\n"
    "\n"
    "TYPE IfcActorSelect = SELECT\n"
    "\t(IfcOrganization\n"
    "\t,IfcPerson);\n"
    "END_TYPE;\n"
    "\n"
    "TYPE IfcComplexNumber = ARRAY [1:2] OF REAL;\n"
    "END_TYPE;\n"
    "\n"
    "ENTITY IfcRoot\n"
    " ABSTRACT SUPERTYPE OF (ONEOF\n"
    "\t(IfcObjectDefinition));\n"
    "\tGlobalId : IfcLabel;\n"
    "\tName : OPTIONAL IfcLabel;\n"
    "END_ENTITY;\n"
    "\n"
    "ENTITY IfcWall\n"
    " SUBTYPE OF (IfcRoot);\n"
    "\tPredefinedType : OPTIONAL IfcWallTypeEnum;\n"
    "\tLayers : SET [1:?] OF IfcLabel;\n"
    " INVERSE\n"
    "\tHasOpenings : SET [0:?] OF IfcRoot FOR GlobalId;\n"
    " WHERE\n"
    "\tCorrectPredefinedType : NOT(EXISTS(PredefinedType));\n"
    "END_ENTITY;\n"
    "\n"
    "END_SCHEMA;\n"
)


def _parse(tmp_path):
    path = tmp_path / "schema.exp"
    path.write_text(SAMPLE, encoding="utf-8")
    return parse_express(str(path))


def test_parses_all_blocks(tmp_path):
    data = _parse(tmp_path)
    assert len(data["types"]) == 4
    assert len(data["entities"]) == 2


def test_simple_type(tmp_path):
    data = _parse(tmp_path)
    label = next(t for t in data["types"] if t["name"] == "IfcLabel")
    assert label["kind"] == "simple"
    assert label["underlying_type"] == "STRING(255)"


def test_enumeration_values(tmp_path):
    data = _parse(tmp_path)
    enum = next(t for t in data["types"] if t["name"] == "IfcWallTypeEnum")
    assert enum["kind"] == "enumeration"
    assert enum["values"] == ["MOVABLE", "SOLIDWALL", "USERDEFINED"]


def test_select_options(tmp_path):
    data = _parse(tmp_path)
    select = next(t for t in data["types"] if t["name"] == "IfcActorSelect")
    assert select["kind"] == "select"
    assert select["options"] == ["IfcOrganization", "IfcPerson"]


def test_aggregate_type(tmp_path):
    data = _parse(tmp_path)
    agg = next(t for t in data["types"] if t["name"] == "IfcComplexNumber")
    assert agg["kind"] == "aggregate"
    assert agg["aggregate_kind"] == "ARRAY"
    assert agg["bounds"] == "1:2"
    assert agg["element_type"] == "REAL"


def test_abstract_entity_and_attributes(tmp_path):
    data = _parse(tmp_path)
    root = next(e for e in data["entities"] if e["name"] == "IfcRoot")
    assert root["abstract"] is True
    assert root["parent"] is None
    names = [a["name"] for a in root["attributes"]]
    assert names == ["GlobalId", "Name"]
    assert root["attributes"][0]["optional"] is False
    assert root["attributes"][1]["optional"] is True
    assert root["attributes"][0]["position"] == 0


def test_entity_inheritance_and_sections(tmp_path):
    data = _parse(tmp_path)
    wall = next(e for e in data["entities"] if e["name"] == "IfcWall")
    assert wall["abstract"] is False
    assert wall["parent"] == "IfcRoot"

    layers = next(a for a in wall["attributes"] if a["name"] == "Layers")
    assert layers["aggregate_kind"] == "SET"
    assert layers["type_ref"] == "IfcLabel"

    assert len(wall["inverse"]) == 1
    inv = wall["inverse"][0]
    assert inv["name"] == "HasOpenings"
    assert inv["entity_ref"] == "IfcRoot"
    assert inv["for_attr"] == "GlobalId"

    assert len(wall["where_rules"]) == 1
    assert wall["where_rules"][0]["name"] == "CorrectPredefinedType"
