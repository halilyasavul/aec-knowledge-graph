"""Step 7 — the knowledge graph's ceiling on the usBridge reference (no LLM).

    python -X utf8 -m eval.usbridge.kg load       # bSDD usBridge -> Neo4j, next to IFC 4.3
    python -X utf8 -m eval.usbridge.kg coverage   # every requirement target, IFC only vs + usBridge

Needs NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD set to the local eval container (the repo's .env
may point at a hosted instance; set them explicitly).

Load. From the bSDD cache (eval/usbridge/bsdd/, offline), with the same pieces the IFC loader uses
(aec_kg.ingest_graph: _run_in_batches, resolve_ifc_type), under labels of its own so no IFC node
is matched, merged or edited: (:UsBridgeClass)-[:HAS_PROPERTY_SET]->(:UsBridgePropertySet)
-[:HAS_PROPERTY]->(:UsBridgeProperty), each also :Bsdd with dictionary = the usBridge URI. A class's
IFC entity, predefined type and object type (from bSDD's relations and its "PredefinedType = /
ObjectType =" description lines) and the standard Pset_/Qto_ sets it names are stored as
properties, not as edges into the IFC graph. IFC node and relationship counts and a checksum of
IFC property values are taken before and after and must be equal.

Coverage. For each requirement facet of specs_expanded.jsonl (and each spec's applicability),
whether its targets exist in the graph:
  entity         every class the facet names is an IFC :Class
  predefinedType a value of the class's PredefinedType enumeration (own or inherited) or an
                 IFC :Class <Entity><TYPE>; with usBridge also a usBridge class with that IFC
                 entity and that predefined/object type
  attribute      the attribute exists on the applicability class or an ancestor
  pset / property / dataType / enumeration   the set exists; the set has the property; the
                 property's IFC type equals the facet's dataType; every enumerated value is an
                 allowed value of the property
  partOf         the whole's class (and predefined type) as above
  classification / material  not graph targets (counted, reported apart)
Writes summary/kg_coverage.json (totals) and reference/kg_coverage.csv (rows, not committed).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import neo4j

from aec_kg.ingest_graph import _run_in_batches, resolve_ifc_type
from eval.usbridge import bsdd

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"          # committed: counts and totals only
DICT = bsdd.DICT_URI
IFC_LABELS = ["Class", "PropertySet", "Property", "Type", "Enumeration", "SelectType", "Attribute", "EnumValue"]


def driver() -> neo4j.Driver:
    for k in ("NEO4J_URI", "NEO4J_PASSWORD"):
        if not os.environ.get(k):
            sys.exit(f"{k} not set; point it at the local eval container explicitly")
    if not os.environ["NEO4J_URI"].startswith(("bolt://localhost", "bolt://127.0.0.1", "neo4j://localhost")):
        sys.exit(f"refusing to write to {os.environ['NEO4J_URI']}: local container only")
    return neo4j.GraphDatabase.driver(os.environ["NEO4J_URI"],
                                      auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]))


def ifc_fingerprint(drv) -> dict:
    with drv.session() as s:
        nodes = {l: s.run(f"MATCH (n:{l}) RETURN count(n) AS c").single()["c"] for l in IFC_LABELS}
        where = " AND ".join(f"NOT a:{x} AND NOT b:{x}" for x in ("UsBridgeClass", "UsBridgePropertySet", "UsBridgeProperty"))
        rels = s.run(f"MATCH (a)-[r]->(b) WHERE {where} RETURN count(r) AS c").single()["c"]
        h = hashlib.sha256()
        for l in IFC_LABELS:
            for r in s.run(f"MATCH (n:{l}) RETURN properties(n) AS p, labels(n) AS ls ORDER BY coalesce(n.code, n.name, n.qualified_name)"):
                h.update(json.dumps([sorted(r["ls"]), r["p"]], sort_keys=True, default=str).encode())
    return {"nodes": nodes, "relationships": rels, "properties_sha256": h.hexdigest()[:16]}


def parse_class(c: dict) -> dict:
    desc = f"{c.get('description') or ''}\n{c.get('definition') or ''}"
    pt = re.search(r"PredefinedType\s*=\s*([A-Z_]+)", desc)
    ot = re.search(r"ObjectType\s*=\s*([A-Za-z0-9_]+)", desc)
    rel = [x.get("relatedClassUri", "").rsplit("/", 1)[-1] for x in c.get("classRelations") or []]
    ents = sorted({*(e.upper() for e in c.get("relatedIfcEntityNames") or []),
                   *(r.upper() for r in rel if r.lower().startswith("ifc"))})
    return {"predefined_type": pt.group(1) if pt else None, "object_type": ot.group(1).upper() if ot else None,
            "related_ifc": ents, "related_ifc_classes": rel}


def load():
    bsdd.OFFLINE = True
    d = bsdd.load()
    drv = driver()
    before = ifc_fingerprint(drv)
    classes = [c for c in d["classes"].values() if c.get("classType") == "Class"]
    props = {p["code"]: p for p in d["properties"].values()}
    cls_rows, pset_rows, rel_cp, rel_pp = [], {}, set(), set()
    for c in classes:
        info = parse_class(c)
        cps = c.get("classProperties") or []
        std = sorted({cp["propertySet"] for cp in cps if cp.get("propertySet") and
                      not str(cp["propertySet"]).startswith("usBr")})
        cls_rows.append({"code": c["code"], "name": c.get("name"), "uri": c["uri"], "definition": c.get("definition"),
                         "description": c.get("description"), "standard_psets": std, **info})
        for cp in cps:
            ps = cp.get("propertySet")
            if not ps or not str(ps).startswith("usBr"):
                continue
            pset_rows[ps] = {"code": ps}
            rel_cp.add((c["code"], ps))
            rel_pp.add((ps, cp["propertyCode"]))
    prop_rows = []
    for code, p in props.items():
        t, src = resolve_ifc_type({"Description": p.get("description"), "Definition": p.get("definition"),
                                   "DataType": p.get("dataType"), "Code": code}, False)
        prop_rows.append({"code": code, "name": p.get("name"), "definition": p.get("definition"),
                          "data_type": p.get("dataType"), "property_value_kind": p.get("propertyValueKind"),
                          "allowed_values": json.dumps([{"Code": v.get("code"), "Value": v.get("value")}
                                                        for v in p.get("allowedValues") or []]) or None,
                          "ifc_type": t, "ifc_type_source": src})
    with drv.session() as s:
        s.run("MATCH (n:Bsdd {dictionary: $d}) DETACH DELETE n", d=DICT)          # idempotent reload
        for l in ("UsBridgeClass", "UsBridgePropertySet", "UsBridgeProperty"):
            s.run(f"CREATE CONSTRAINT {l.lower()}_code IF NOT EXISTS FOR (n:{l}) REQUIRE n.code IS UNIQUE")
    _run_in_batches(drv, """UNWIND $rows AS r CREATE (n:UsBridgeClass:Bsdd {code: r.code}) SET n += r,
                            n.dictionary = $d""".replace("$d", json.dumps(DICT)), "rows", cls_rows)
    _run_in_batches(drv, """UNWIND $rows AS r CREATE (n:UsBridgePropertySet:Bsdd {code: r.code})
                            SET n.dictionary = $d""".replace("$d", json.dumps(DICT)), "rows", list(pset_rows.values()))
    _run_in_batches(drv, """UNWIND $rows AS r CREATE (n:UsBridgeProperty:Bsdd {code: r.code}) SET n += r,
                            n.dictionary = $d""".replace("$d", json.dumps(DICT)), "rows", prop_rows)
    _run_in_batches(drv, """UNWIND $rows AS r MATCH (c:UsBridgeClass {code: r[0]}), (p:UsBridgePropertySet {code: r[1]})
                            MERGE (c)-[:HAS_PROPERTY_SET]->(p)""", "rows", [list(x) for x in sorted(rel_cp)])
    missing = sorted({pc for _, pc in rel_pp if pc not in props})
    _run_in_batches(drv, """UNWIND $rows AS r MATCH (s:UsBridgePropertySet {code: r[0]}), (p:UsBridgeProperty {code: r[1]})
                            MERGE (s)-[:HAS_PROPERTY]->(p)""", "rows", [list(x) for x in sorted(rel_pp)])
    wb = workbook_definitions(drv)
    after = ifc_fingerprint(drv)
    with drv.session() as s:
        counts = {l: s.run(f"MATCH (n:{l}) RETURN count(n) AS c").single()["c"]
                  for l in ("UsBridgeClass", "UsBridgePropertySet", "UsBridgeProperty")}
        counts["HAS_PROPERTY_SET"] = s.run("MATCH (:UsBridgeClass)-[r:HAS_PROPERTY_SET]->() RETURN count(r) AS c").single()["c"]
        counts["HAS_PROPERTY"] = s.run("MATCH (:UsBridgePropertySet)-[r:HAS_PROPERTY]->() RETURN count(r) AS c").single()["c"]
    drv.close()
    out = {"dictionary": DICT, "loaded": counts, "class_properties_without_property_record": missing,
           "ifc_before": before, "ifc_after": after, "ifc_untouched": before == after,
           "ifc_type_sources": dict(Counter(r["ifc_type_source"] for r in prop_rows)),
           "workbook_property_definitions": wb}
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "kg_load.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    if before != after:
        sys.exit("IFC part of the graph changed")


def workbook_definitions(drv) -> dict:
    """The workbook's property-definition rows — the source the bSDD entries were made from: set,
    property, IFC data type, PropertyType, enumeration, description, example. Loaded onto the
    usBridge set->property relationship (rel.ifc_type, rel.allowed_values; readers take
    coalesce(rel, node), as for IFC). NOT loaded: the per-entity "IDS Cardinality" column and which
    entity tab a set appears on (the entity -> spec structure). Set names get the propertySet
    corrections of reference/corrections.json (the workbook shares 'usBrPset_Expansion Joint')."""
    corr = {c["find"]: c["replace"] for c in json.loads((ROOT / "reference" / "corrections.json")
                                                         .read_text(encoding="utf-8"))["corrections"]
            if c["field"] == "propertySet"}
    defs: dict = {}
    for line in open(ROOT / "reference" / "workbook_entities.jsonl", encoding="utf-8"):
        e = json.loads(line)
        for ps in e["psets"]:
            if ps["source"] != "usbridge":
                continue
            name = corr.get(ps["pset"], ps["pset"])
            for q in ps["properties"]:
                d = defs.setdefault((name, q["name"]), {"pset": name, "code": q["name"], "variants": set()})
                d["variants"].add((q.get("data_type"), q.get("property_type"), tuple(q.get("enumeration") or ()),
                                   q.get("description"), q.get("example")))
    rows, conflicts = [], []
    for (ps, code), d in sorted(defs.items()):
        types = {v[0] for v in d["variants"] if v[0]}
        if len(types) > 1:
            conflicts.append([ps, code, sorted(types)])
        v = max(d["variants"], key=lambda x: (x[0] is not None, len(x[2])))
        t = (v[0] or "").upper() or None
        rows.append({"pset": ps, "code": code, "ifc_type": t if t and t.startswith("IFC") else None,
                     "property_type": v[1], "description": v[3], "example": v[4],
                     "allowed_values": json.dumps([{"Value": x} for x in v[2]]) if v[2] else None})
    _run_in_batches(drv, """UNWIND $rows AS r
        MERGE (s:UsBridgePropertySet {code: r.pset})
          ON CREATE SET s:Bsdd, s.dictionary = $d, s.source = 'workbook'
        MERGE (p:UsBridgeProperty {code: r.code})
          ON CREATE SET p:Bsdd, p.dictionary = $d, p.source = 'workbook', p.definition = r.description
        MERGE (s)-[rel:HAS_PROPERTY]->(p)
          ON CREATE SET rel.source = 'workbook'
        SET rel.ifc_type = r.ifc_type, rel.ifc_type_source = CASE WHEN r.ifc_type IS NULL THEN null ELSE 'workbook' END,
            rel.property_type = r.property_type, rel.example = r.example,
            rel.allowed_values = coalesce(r.allowed_values, rel.allowed_values)""".replace("$d", json.dumps(DICT)),
                    "rows", rows)
    with drv.session() as s:
        new = s.run("""MATCH (:UsBridgePropertySet)-[r:HAS_PROPERTY {source: 'workbook'}]->() RETURN count(r) AS c""").single()["c"]
    return {"definitions": len(rows), "with_ifc_type": sum(1 for r in rows if r["ifc_type"]),
            "with_enumeration": sum(1 for r in rows if r["allowed_values"]),
            "set_property_pairs_not_in_bsdd": new, "data_type_conflicts": conflicts}


# --------------------------------------------------------------------------- coverage
def names_of(v: str | None) -> list[str]:
    if not v:
        return []
    if v.startswith("RESTRICTION("):
        return re.findall(r"enumeration=([^,)]+)", v)
    return [v]


class Graph:
    def __init__(self, drv):
        with drv.session() as s:
            self.classes = {r["c"].upper(): r["c"] for r in s.run("MATCH (c:Class) RETURN c.code AS c")}
            self.parents = defaultdict(set)
            for r in s.run("MATCH (a:Class)-[:INHERITS_FROM]->(b:Class) RETURN a.code AS a, b.code AS b"):
                self.parents[r["a"].upper()].add(r["b"].upper())
            self.attrs = defaultdict(set)
            for r in s.run("MATCH (c:Class)-[:HAS_ATTRIBUTE]->(a:Attribute) RETURN c.code AS c, a.name AS a"):
                self.attrs[r["c"].upper()].add(r["a"])
            self.ptypes = defaultdict(set)
            for r in s.run("""MATCH (c:Class)-[:HAS_ATTRIBUTE]->(a:Attribute {name: 'PredefinedType'})
                              -[:ATTRIBUTE_TYPE]->(:Enumeration)-[:HAS_VALUE]->(v:EnumValue)
                              RETURN c.code AS c, v.value AS v"""):
                self.ptypes[r["c"].upper()].add(r["v"].upper())
            self.psets = {r["c"] for r in s.run("MATCH (p:PropertySet) RETURN p.code AS c")}
            self.props = {}
            for r in s.run("""MATCH (s:PropertySet)-[rel:HAS_PROPERTY]->(p:Property)
                              RETURN s.code AS s, p.code AS p, coalesce(rel.ifc_type, p.ifc_type) AS t,
                                     p.allowed_values AS av"""):
                self.props[(r["s"], r["p"])] = (r["t"], _values(r["av"]))
            self.u_psets = {r["c"] for r in s.run("MATCH (p:UsBridgePropertySet) RETURN p.code AS c")}
            self.u_props = {}
            for r in s.run("""MATCH (s:UsBridgePropertySet)-[rel:HAS_PROPERTY]->(p:UsBridgeProperty)
                              RETURN s.code AS s, p.code AS p, coalesce(rel.ifc_type, p.ifc_type) AS t,
                                     p.allowed_values AS av, rel.allowed_values AS rav"""):
                self.u_props[(r["s"], r["p"])] = (r["t"], _values(r["av"]) | _values(r["rav"]))
            self.u_types = defaultdict(set)
            for r in s.run("""MATCH (c:UsBridgeClass) RETURN c.related_ifc AS e, c.predefined_type AS p,
                              c.object_type AS o"""):
                for e in r["e"] or []:
                    for v in (r["p"], r["o"]):
                        if v:
                            self.u_types[e.upper()].add(v.upper())

    def ancestors(self, c: str) -> set[str]:
        out, todo = set(), [c]
        while todo:
            x = todo.pop()
            for p in self.parents.get(x, ()):
                if p not in out:
                    out.add(p)
                    todo.append(p)
        return out

    def has_class(self, c: str) -> bool:
        return c.upper() in self.classes

    def has_ptype(self, cls: str, pt: str, usb: bool) -> bool:
        c, pt = cls.upper(), pt.upper()
        lineage = {c} | self.ancestors(c)
        if any(pt in self.ptypes.get(x, ()) for x in lineage) or f"{c}{pt}" in self.classes:
            return True
        return usb and pt in self.u_types.get(c, set())

    def has_attr(self, cls: str, name: str) -> bool:
        c = cls.upper()
        return any(name in self.attrs.get(x, ()) for x in {c} | self.ancestors(c))


def _values(av) -> set[str]:
    if not av:
        return set()
    try:
        return {str(x.get("Value") or x.get("Code")) for x in json.loads(av)}
    except Exception:
        return set()


def check_facet(g: Graph, f: dict, app_classes: list[str], usb: bool) -> dict:
    kind = f["facet"]
    if kind in ("classification", "material"):
        return {"graph_target": False}
    res = {"graph_target": True}
    if kind in ("entity", "partOf"):          # a listed type need only exist on one listed class
        cls = names_of(f.get("name") if kind == "entity" else f.get("entity"))
        pts = names_of(f.get("predefinedType") if kind == "entity" else f.get("entityPredefinedType"))
        res["entity"] = all(g.has_class(c) for c in cls)
        if pts:
            res["predefinedType"] = all(any(g.has_ptype(c, p, usb) for c in cls) for p in pts)
    elif kind == "attribute":
        name = f.get("name") or ""
        res["attribute"] = bool(app_classes) and all(g.has_attr(c, name) for c in app_classes)
    elif kind == "property":
        ps, bn = f.get("propertySet") or "", f.get("baseName") or ""
        if ps.startswith("RESTRICTION("):
            return {"graph_target": False}
        res["pset"] = ps in g.psets or (usb and ps in g.u_psets)
        if not bn.startswith("RESTRICTION("):
            hit = g.props.get((ps, bn)) or (g.u_props.get((ps, bn)) if usb else None)
            res["property"] = hit is not None
            if f.get("dataType"):
                res["dataType"] = bool(hit) and (hit[0] or "").upper() == f["dataType"].upper()
            vals = names_of(f.get("value")) if (f.get("value") or "").startswith("RESTRICTION(enumeration") else []
            if vals:
                res["enumeration"] = bool(hit) and set(vals) <= hit[1]
                # the IDS upper-cases usBridge values bSDD writes 'Shop'; reported, not in "all"
                res["enumeration_ci"] = bool(hit) and {v.upper() for v in vals} <= {v.upper() for v in hit[1]}
    res["all"] = all(v for k, v in res.items() if k not in ("graph_target", "enumeration_ci"))
    return res


def coverage():
    drv = driver()
    g = Graph(drv)
    drv.close()
    specs = [json.loads(l) for l in open(ROOT / "reference" / "specs_expanded.jsonl", encoding="utf-8")]
    rows = []
    for sp in specs:
        a = sp["applies_to"] or {}
        app_cls = names_of(a.get("entity"))
        app_facet = {"facet": "entity", "name": a.get("entity"), "predefinedType": a.get("predefinedType")}
        targets = [("applicability", -1, app_facet)] + [("requirement", f["req_index"], f) for f in sp["requirements"]]
        for side, idx, f in targets:
            r0, r1 = check_facet(g, f, app_cls, False), check_facet(g, f, app_cls, True)
            rows.append({"spec_id": sp["spec_id"], "side": side, "req_index": idx, "kind": f["facet"],
                         "origin": f.get("origin", ""), "target": json.dumps({k: f.get(k) for k in
                         ("name", "predefinedType", "propertySet", "baseName", "dataType", "value", "entity",
                          "entityPredefinedType") if f.get(k)}),
                         **{f"ifc_{k}": v for k, v in r0.items()}, **{f"usb_{k}": v for k, v in r1.items()}})
    with open(ROOT / "reference" / "kg_coverage.csv", "w", newline="", encoding="utf-8") as fh:
        cols = []
        for r in rows:
            cols += [k for k in r if k not in cols]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    def table(rs):
        out = {}
        for check in ("entity", "predefinedType", "attribute", "pset", "property", "dataType", "enumeration",
                      "enumeration_ci", "all"):
            have = [r for r in rs if f"ifc_{check}" in r and r["ifc_graph_target"]]
            if have:
                out[check] = {"n": len(have), "ifc": sum(bool(r[f"ifc_{check}"]) for r in have),
                              "ifc+usbridge": sum(bool(r[f"usb_{check}"]) for r in have)}
        return out

    req = [r for r in rows if r["side"] == "requirement"]
    out = {"requirement_facets": len(req),
           "not_graph_targets": dict(Counter(r["kind"] for r in req if not r["ifc_graph_target"])),
           "by_check": table(req),
           "by_check_property_facets_usbr_vs_std": {
               "usBrPset": table([r for r in req if r["kind"] == "property" and '"usBr' in r["target"]]),
               "standard Pset_/Qto_": table([r for r in req if r["kind"] == "property" and '"usBr' not in r["target"]])},
           "applicability": table([r for r in rows if r["side"] == "applicability"]),
           "missing_examples_with_usbridge": {
               check: sorted({r["target"] for r in req if r.get(f"usb_{check}") is False})[:12]
               for check in ("predefinedType", "attribute", "pset", "property", "dataType", "enumeration")}}
    (ROOT / "reference" / "kg_coverage_missing.json").write_text(json.dumps(
        out.pop("missing_examples_with_usbridge"), indent=1), encoding="utf-8")   # quotes the IDS: not committed
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "kg_coverage.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "missing_examples_with_usbridge"}, indent=1))


if __name__ == "__main__":
    {"load": load, "coverage": coverage}[sys.argv[1]]()
