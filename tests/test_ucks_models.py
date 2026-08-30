"""Tests for UCKS entity models and the YAML round-trip used by
save_entity_yaml / reingest_ucks (no database required)."""

import pytest
from pydantic import ValidationError

from aec_kg.ucks.models import EntityDef
from aec_kg.ucks.pipeline import _entity_to_yaml_dict
from aec_kg.reingest_ucks import load_entity_yaml

BRIDGE_PIER = {
    "id": "bridge_pier",
    "name": "Bridge Pier",
    "description": "A vertical support structure transferring deck loads to the foundation.",
    "sector": "infrastructure",
    "domain": "structural",
    "parent": "structural_element",
    "property_groups": [
        {
            "id": "geometric_properties",
            "name": "Geometric Properties",
            "properties": [
                {"id": "height", "name": "Height", "data_type": "real", "unit": "m"},
                {
                    "id": "material_type",
                    "name": "Material Type",
                    "data_type": "enum",
                    "enumeration": {
                        "id": "material_enum",
                        "values": ["CONCRETE", "STEEL", "COMPOSITE"],
                    },
                },
            ],
        }
    ],
    "relationships": [
        {
            "type": "supports",
            "target": "bridge_deck",
            "cardinality": "one_to_many",
            "description": "Deck elements supported by this pier.",
        }
    ],
}


def test_entity_validates():
    entity = EntityDef(**BRIDGE_PIER)
    assert entity.id == "bridge_pier"
    assert entity.property_groups[0].properties[0].unit == "m"
    assert entity.relationships[0].target == "bridge_deck"


def test_entity_requires_core_fields():
    with pytest.raises(ValidationError):
        EntityDef(id="x", name="X")  # missing description/sector/domain


def test_yaml_round_trip(tmp_path):
    entity = EntityDef(**BRIDGE_PIER)
    yaml_dict = _entity_to_yaml_dict(entity)

    # Matches the on-disk layout: sector/domain at top level, rest nested
    assert yaml_dict["schema"] == "ucks/0.1"
    assert yaml_dict["sector"] == "infrastructure"
    assert yaml_dict["entity"]["id"] == "bridge_pier"

    import yaml

    path = tmp_path / "bridge_pier.yaml"
    path.write_text(
        yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    restored = load_entity_yaml(path)
    assert restored.id == entity.id
    assert restored.sector == entity.sector
    assert restored.parent == entity.parent
    assert len(restored.property_groups) == 1
    props = restored.property_groups[0].properties
    assert props[1].enumeration.values == ["CONCRETE", "STEEL", "COMPOSITE"]
    assert restored.relationships[0].cardinality == "one_to_many"


def test_bundled_example_entities_load():
    """Every UCKS YAML shipped in data/ucks_entities must validate."""
    from aec_kg.ucks.pipeline import UCKS_OUTPUT_DIR

    files = sorted(UCKS_OUTPUT_DIR.rglob("*.yaml"))
    assert files, "expected bundled example entities in data/ucks_entities"
    for f in files:
        entity = load_entity_yaml(f)
        assert entity.id == f.stem
