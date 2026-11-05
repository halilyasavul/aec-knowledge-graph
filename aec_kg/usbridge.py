"""The bSDD usBridge dictionary (usTransportation/usBridge/1) in the knowledge graph.

Loaded next to IFC 4.3 by eval/usbridge/kg.py under labels of its own:
    (:UsBridgeClass)-[:HAS_PROPERTY_SET]->(:UsBridgePropertySet)-[:HAS_PROPERTY]->(:UsBridgeProperty)
A usBridge class names its IFC entity (related_ifc), predefined/object type and the standard
Pset_/Qto_ sets bSDD lists for it (standard_psets). The IFC data type and enumeration of a
usBridge property sit on the set->property relationship (rel.ifc_type, rel.allowed_values, from
the workbook's property definitions) or on the property node (bSDD); readers take coalesce(rel, node).

The MCP server reads these only when started with --dictionaries ifc,usbridge. Every record
returned here carries "dictionary": "usBridge".
"""
from __future__ import annotations

import json

from aec_kg.neuro_agent import _get_driver

DICTIONARY = "usBridge"


def _values(*raw) -> list:
    out, seen = [], set()
    for r in raw:
        if not r:
            continue
        try:
            for v in json.loads(r):
                key = str(v.get("Value") or v.get("Code"))
                if key not in seen:
                    seen.add(key)
                    out.append({"Value": key})
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def search(term: str, limit: int = 40) -> list[dict]:
    """usBridge classes whose code or name contains `term` (case-insensitive)."""
    q = """MATCH (c:UsBridgeClass)
           WHERE toLower(c.name) CONTAINS toLower($t) OR toLower(c.code) CONTAINS toLower($t)
           RETURN c.code AS code, c.name AS name, c.definition AS definition, c.related_ifc AS ifc,
                  c.predefined_type AS pt, c.object_type AS ot
           ORDER BY c.code LIMIT $n"""
    with _get_driver().session() as s:
        rows = list(s.run(q, t=term, n=limit))
    out = []
    for r in rows:
        d = (r["definition"] or "").strip().replace("\n", " ")
        rec = {"code": r["code"], "name": r["name"], "definition": d[:160] + ("…" if len(d) > 160 else ""),
               "dictionary": DICTIONARY, "ifc_entity": (r["ifc"] or [None])[0]}
        if r["pt"]:
            rec["predefinedType"] = r["pt"]
        if r["ot"]:
            rec["objectType"] = r["ot"]
        out.append(rec)
    return out


def class_index(code: str) -> dict | None:
    """A usBridge class: its IFC entity and type, its usBridge property sets with property codes,
    and the standard Pset_/Qto_ sets bSDD lists for it. None if `code` is not a usBridge class."""
    q = """MATCH (c:UsBridgeClass {code: $code})
           OPTIONAL MATCH (c)-[:HAS_PROPERTY_SET]->(s:UsBridgePropertySet)-[:HAS_PROPERTY]->(p:UsBridgeProperty)
           RETURN c.code AS code, c.name AS name, c.definition AS definition, c.related_ifc AS ifc,
                  c.predefined_type AS pt, c.object_type AS ot, c.standard_psets AS std,
                  s.code AS pset, p.code AS prop ORDER BY s.code, p.code"""
    with _get_driver().session() as s:
        rows = list(s.run(q, code=code))
    if not rows:
        return None
    f = rows[0]
    out = {"class_code": f["code"], "class_name": f["name"], "class_definition": f["definition"],
           "dictionary": DICTIONARY, "ifc_entity": (f["ifc"] or [None])[0],
           "predefinedType": f["pt"], "objectType": f["ot"],
           "standard_property_sets": f["std"] or [], "property_sets": {}}
    for r in rows:
        if r["pset"]:
            codes = out["property_sets"].setdefault(r["pset"], [])
            if r["prop"] and r["prop"] not in codes:
                codes.append(r["prop"])
    return out


def classes_for_ifc(ifc_code: str) -> list[dict]:
    """usBridge classes mapped to an IFC entity, with their type and usBridge set names."""
    q = """MATCH (c:UsBridgeClass) WHERE toUpper($code) IN [x IN coalesce(c.related_ifc, []) | toUpper(x)]
           OPTIONAL MATCH (c)-[:HAS_PROPERTY_SET]->(s:UsBridgePropertySet)
           RETURN c.code AS code, c.name AS name, c.predefined_type AS pt, c.object_type AS ot,
                  collect(DISTINCT s.code) AS psets ORDER BY c.code"""
    with _get_driver().session() as s:
        rows = list(s.run(q, code=ifc_code))
    return [{"code": r["code"], "name": r["name"], "predefinedType": r["pt"], "objectType": r["ot"],
             "property_sets": sorted(x for x in r["psets"] if x), "dictionary": DICTIONARY} for r in rows]


def pset_detail(code: str) -> dict | None:
    """One usBridge property set in full, in the shape of get_pset_detail. None if unknown."""
    q = """MATCH (s:UsBridgePropertySet {code: $code})
           OPTIONAL MATCH (s)-[rel:HAS_PROPERTY]->(p:UsBridgeProperty)
           OPTIONAL MATCH (c:UsBridgeClass)-[:HAS_PROPERTY_SET]->(s)
           RETURN s.code AS pset, collect(DISTINCT c.code) AS classes, p.code AS code, p.name AS name,
                  p.definition AS definition, p.data_type AS data_type, p.property_value_kind AS kind,
                  coalesce(rel.ifc_type, p.ifc_type) AS ifc_type, rel.allowed_values AS rav,
                  p.allowed_values AS pav ORDER BY p.code"""
    with _get_driver().session() as s:
        rows = list(s.run(q, code=code))
    if not rows:
        return None
    out = {"pset_code": rows[0]["pset"], "pset_name": rows[0]["pset"], "pset_definition": None,
           "dictionary": DICTIONARY, "applies_to": sorted(x for x in rows[0]["classes"] if x), "properties": []}
    seen = set()
    for r in rows:
        if r["code"] is None or r["code"] in seen:
            continue
        seen.add(r["code"])
        e = {"code": r["code"], "name": r["name"], "definition": r["definition"], "data_type": r["data_type"],
             "property_value_kind": r["kind"], "allowed_values": _values(r["rav"], r["pav"])}
        if r["ifc_type"]:
            e["ifc_type"] = r["ifc_type"]
        out["properties"].append(e)
    return out
