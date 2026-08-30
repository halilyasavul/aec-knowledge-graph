"""Tests for IDS generation: Pydantic validation, XML serialization, and
XSD validation against the bundled buildingSMART ids.xsd."""

from aec_kg.ids.pipeline import generate_ids_from_json

VALID_DOC = {
    "info": {"title": "Wall Requirements"},
    "specifications": [
        {
            "name": "Wall fire rating",
            "ifcVersion": "IFC4",
            "applicability": {
                "entity": {"name": {"simpleValue": "IFCWALL"}},
            },
            "requirements": {
                "properties": [
                    {
                        "propertySet": {"simpleValue": "Pset_WallCommon"},
                        "baseName": {"simpleValue": "FireRating"},
                        "dataType": "IFCLABEL",
                        "cardinality": "required",
                    }
                ],
                "attributes": [
                    {"name": {"simpleValue": "Name"}, "cardinality": "required"}
                ],
            },
        }
    ],
}


def test_valid_document_generates_xsd_valid_xml():
    result = generate_ids_from_json(VALID_DOC)
    assert result.get("success") is True, result
    assert result["spec_count"] == 1
    xml = result["ids_xml"]
    assert "IFCWALL" in xml
    assert "Pset_WallCommon" in xml
    assert 'xmlns:ids="http://standards.buildingsmart.org/IDS"' in xml


def test_missing_title_reports_validation_error():
    bad = {"info": {}, "specifications": VALID_DOC["specifications"]}
    result = generate_ids_from_json(bad)
    assert "validation_errors" in result
    assert any("title" in e for e in result["validation_errors"])


def test_value_requires_exactly_one_variant():
    doc = {
        "info": {"title": "t"},
        "specifications": [
            {
                "name": "s",
                "applicability": {
                    "entity": {
                        "name": {
                            "simpleValue": "IFCWALL",
                            "restriction": {"enumerations": ["IFCWALL"]},
                        }
                    }
                },
            }
        ],
    }
    result = generate_ids_from_json(doc)
    assert "validation_errors" in result


def test_case_is_normalized_algorithmically():
    """IFC identifiers must come out UPPERCASE regardless of what the LLM
    produced (e.g. 'IFCLENGTHMEasure' seen in the wild)."""
    doc = {
        "info": {"title": "Case test"},
        "specifications": [
            {
                "name": "Case normalization",
                "ifcVersion": "ifc4",
                "applicability": {
                    "entity": {
                        "name": {"simpleValue": "IfcWall"},
                        "predefinedType": {"simpleValue": "solidwall"},
                    }
                },
                "requirements": {
                    "properties": [
                        {
                            "propertySet": {"simpleValue": "Pset_WallCommon"},
                            "baseName": {"simpleValue": "FireRating"},
                            "dataType": "IFCLENGTHMEasure",
                        }
                    ]
                },
            }
        ],
    }
    result = generate_ids_from_json(doc)
    assert result.get("success") is True, result
    xml = result["ids_xml"]
    assert 'dataType="IFCLENGTHMEASURE"' in xml
    assert "<ids:simpleValue>IFCWALL</ids:simpleValue>" in xml
    assert "<ids:simpleValue>SOLIDWALL</ids:simpleValue>" in xml
    assert 'ifcVersion="IFC4"' in xml
    # Property set / property names keep their original case
    assert "Pset_WallCommon" in xml
    assert "FireRating" in xml


def test_restriction_enumeration_round_trips():
    doc = {
        "info": {"title": "Enum restriction"},
        "specifications": [
            {
                "name": "Restricted walls",
                "ifcVersion": "IFC4",
                "applicability": {
                    "entity": {
                        "name": {
                            "restriction": {
                                "base": "xs:string",
                                "enumerations": ["IFCWALL", "IFCWALLSTANDARDCASE"],
                            }
                        }
                    }
                },
            }
        ],
    }
    result = generate_ids_from_json(doc)
    assert result.get("success") is True, result
    assert "IFCWALLSTANDARDCASE" in result["ids_xml"]
