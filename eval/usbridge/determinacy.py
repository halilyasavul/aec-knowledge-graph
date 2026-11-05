"""Step 6 — determinacy: which reference requirements does an IDM-1 row state?

    python -X utf8 -m eval.usbridge.determinacy

For every requirement facet of every reference spec of every item (specs_expanded.jsonl), decide
`determined` (an IDM-1 row in *that item's* request states it; evidence = the row) or
`undetermined` (HDR added it for IDM 2.0). The whole-document item may cite any IDM-1 row, so the
same facet can be undetermined for an entity item and determined for the document item (pay item
quantities: stated once, in 4.1.2 Contract Information).

Machine-made, deterministic, NOT reviewed by a human (same standing as the dev set's
eval/annotations/determinacy.jsonl). Rules, in order:

  property   the IDS name, split at camel case (SNBIElementNumber -> snbi element number), folded
             (case, plural, stopwords, synonyms: begin=start, elev=elevation, ...) must have every
             word in one IDM row, read as "<property>" or "<property set> <property>", and cover at
             least half that row's words  -> determined (method lexical-exact | lexical-cover).
             A data type is never a reason for undetermined (schema knowledge under test).
             value: an enumeration is determined when every allowed value except OTHER/NOTKNOWN/
             UNSET/USERDEFINED/NOTDEFINED appears in the item's request; otherwise scope=value.
  attribute  Name <- an IDM row "Identification" or "...Name"; Description <- "Description";
             ObjectType/PredefinedType <- "Type" or a "Type(s)" property set; Tag <- "Identification";
             everything else (CompositionType, LongName, ...) undetermined.
  material   <- an IDM row containing "Material".
  classification  <- "Pay Item"/"Item Number" (pay item classification); else undetermined.
  partOf     <- the subsection: IFCBRIDGEPART SUPERSTRUCTURE for 4.1.6, SUBSTRUCTURE for 4.1.7
             (method section); else undetermined. "Connected by" is not read as containment.
  entity     (requirement-side predefined-type whitelists) undetermined.
  whole set  a set-level facet that was not expanded (prohibited sets; sets with no spec):
             undetermined — the IDM never prohibits and never names a set.
IDM cardinality: "All listed properties are required (when present)", so every determined facet
carries idm_cardinality=required; `cardinality_conflict` marks a determined facet the reference
makes optional.

Writes eval/usbridge/annotations/determinacy.jsonl and summary/determinacy_summary.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"          # committed: counts and totals only
OUT = ROOT / "annotations"
STOP = {"at", "of", "the", "to", "for", "and", "or", "a", "an", "in", "on", "by", "from", "between", "with",
        "e", "g", "eg", "etc", "is", "per", "each", "if", "any", "yes", "no", "example"}
SYN = {"begin": "start", "begins": "start", "beginning": "start", "ends": "end", "elev": "elevation",
       "elevations": "elevation", "sta": "station", "dia": "diameter", "diam": "diameter", "thk": "thickness",
       "qty": "quantity", "id": "identification", "identifier": "identification", "ident": "identification",
       "num": "number", "no": "number", "nr": "number", "len": "length", "ht": "height", "wt": "weight",
       "spacing": "spacing", "centerline": "centerline", "cl": "centerline", "pc": "precast", "ps": "prestressed",
       "fy": "yield", "fc": "strength", "pier": "pier", "bent": "pier", "girders": "girder", "beam": "girder",
       "beams": "girder", "horiz": "horizontal", "vert": "vertical", "long": "longitudinal", "trans": "transverse",
       "min": "minimum", "max": "maximum", "approx": "approximate", "skewangle": "skew", "angle": "angle"}
CATCH_ALL = {"OTHER", "NOTKNOWN", "UNSET", "USERDEFINED", "NOTDEFINED"}

# Readings: the 418 distinct lexical near-misses (best IDM row covering >= half) were read once by
# the annotator (Claude, 2026-11-04); these are the ones where the IDM row states the same quantity.
# Not accepted, by rule: the generic "General Properties" rows (Type, Location, Description,
# Quantity, Identification), which every IDM entity lists; min/max/offset variants of a single
# stated value; a different concept with a shared word (camber vs deflection, prebore vs socket).
# IDS baseName -> [(IDM entity, property set, property)]
READINGS: dict[str, list[tuple[str, str, str]]] = {
    "SacrificialWearingThickness": [("Approach Slabs", "Dimension", "Slab Sacrificial Thickness"),
                                    ("Deck", "Dimension", "Deck Sacrificial Thickness")],
    "MinimumHorizontalClearanceLeft": [("Bridge Configuration", "Clearance", "Minimum Horizontal Clearance")],
    "MinimumHorizontalClearanceRight": [("Bridge Configuration", "Clearance", "Minimum Horizontal Clearance")],
    "RoadwayMinimumVerticalClearance": [("Bridge Configuration", "Clearance", "Minimum Vertical Clearance")],
    "StationBackBearing": [("Bridge Control Information", "Stations", "Station at Centerline of Bearings at Pier")],
    "StationAheadBearing": [("Bridge Control Information", "Stations", "Station at Centerline of Bearings at Pier")],
    "CoatingSystem": [("Coating", "Properties", "System")],
    "CoatingType": [("Coating", "Properties", "Type")],
    "NominalDiameter": [("Conduit", "Geometry", "Diameter")],
    "PayItemReference": [("Contract Information", "Pay Item Information", "Item Number")],
    "UnitOfMeasure": [("Contract Information", "Pay Item Information", "Units")],
    "PayQuantity": [("Contract Information", "Pay Item Information", "Total Quantity")],
    "Length": [("Drill and Bond Dowel Bar", "Properties", "Dowel Bar Length"),
               ("Pier Cap", "Dimensions", "Cap Beam Length"),
               ("Pier Column", "Dimensions", "Pier Column Length")],
    "PlateThickness": [("Fill Plate", "Dimensions", "Thickness"), ("Gusset", "Dimensions", "Thickness"),
                       ("Splice Plate", "Dimensions", "Thickness"), ("Stiffener", "Dimensions", "Thickness")],
    "HorizontalLengthMeasure": [("Fill Plate", "Dimensions", "Length"), ("Gusset", "Dimensions", "Length"),
                                ("Stiffener", "Dimensions", "Length")],
    "NetWeight": [("Stiffener", "Properties", "Stiffener Weight")],
    "AllowableBearingPressure": [("Footing/Pile Cap/Drilled Shaft Cap", "Spread Footing Properties", "Bearing Pressure")],
    "MidSpanCamberAtRelease": [("Girder", "Concrete Girder Camber and Deflection", "Camber at Prestressing Release")],
    "CompositeDeadLoadDeflection": [("Girder", "Concrete Girder Camber and Deflection", "Deflection Due to Composite Loads")],
    "NonCompositeSlabDeflection": [("Girder", "Concrete Girder Camber and Deflection", "Deflection Due to Non-Composite Loads")],
    "NonCompositeSteelDeflection": [("Girder", "Concrete Girder Camber and Deflection", "Deflection Due to Non-Composite Loads")],
    "LiftingLoopLocation": [("Girder", "Precast/Prestressed Concrete Girder", "Lifting Location")],
    "HaunchDepth": [("Haunch", "Dimension", "Haunch Thickness (Theoretical Haunch Height)")],
    "FeatureName": [("Identification", "Under Feature Identities", "Feature Name (e.g., Highway, River, Creek, etc.)"),
                    ("Project Descriptions", "Miscellaneous Data", "Feature Intersected")],
    "HydraulicFeatureName": [("Identification", "Under Feature Identities", "Feature Name (e.g., Highway, River, Creek, etc.)")],
    "RoadwayName": [("Identification", "Primary Road", "Local Road Number/Name")],
    "RefLatitude": [("Location", "Coordinates", "Latitude")],
    "RefLongitude": [("Location", "Coordinates", "Longitude")],
    "ReinforcingGrade": [("Longitudinal Bar", "Properties", "Bar Grade"), ("Transverse Reinforcement", "Properties", "Grade")],
    "MinimumSpliceLength": [("Longitudinal Bar", "Dimensions", "Lap Splice Length")],
    "ModelPreparationDate": [("Metadata", "Dates", "Prepared On")],
    "PSEDate": [("Metadata", "Dates", "Plans Specs & Estimation Date")],
    "Depth": [("Pier Column", "Dimensions", "Pier Column Depth")],
    "Diameter": [("Pier Column", "Dimensions", "Pier Column Diameter")],
    "Width": [("Pier Column", "Dimensions", "Pier Column Width")],
    "ColumnHeight": [("Pier Column", "Dimensions", "Pier Column Length")],
    "BatterLongitudinal": [("Pile", "Dimensions", "Batter")],
    "BatterTransverse": [("Pile", "Dimensions", "Batter")],
    "CalculatedElongation": [("Post-Tensioning", "Calculations", "Elongation of Strands")],
    "DuctType": [("Post-Tensioning", "Properties", "Type of Ducts Used (Metal/Polyethylene)")],
    "GroutVentLocations": [("Post-Tensioning", "Dimensions", "Grout Inlet Port Location")],
    "TendonType": [("Prestressing", "Properties", "Strand Type")],
    "AnnualAverageDailyTraffic": [("Project Descriptions", "Design Data", "Average Daily Traffic")],
    "AnnualAverageDailyTruckTraffic": [("Project Descriptions", "Design Data", "Average Daily Truck Traffic")],
    "ShapeName": [("Soldier Pile Wall", "Pile", "Shape")],
    "FitCondition": [("Transverse Member", "Work Point Definition",
                      "Fit Condition for Detailing (No Load, Steel Dead Load, Total Dead Load)")],
}


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) else w


def words(s: str | None) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s or "")          # camel case
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)              # SNBIElement -> SNBI Element
    out = []
    for t in re.findall(r"[a-z0-9]+", s.lower()):
        t = SYN.get(t, t)
        t = singular(t)
        if t not in STOP:
            out.append(t)
    if "skew" in out and "angle" in out:
        out.remove("angle")
    return out


def restriction_values(v: str | None) -> list[str]:
    if not v:
        return []
    if v.startswith("RESTRICTION("):
        return [x for k, x in re.findall(r"(enumeration)=([^,)]*)", v)]
    return [v]


class Rows:
    """The IDM rows an item's request contains."""

    def __init__(self, ents: list[dict]):
        self.rows = []
        for e in ents:
            for g in e["property_groups"]:
                for p in g["properties"]:
                    self.rows.append({"entity": e["entity"], "group": g["name"], "property": p,
                                      "w_prop": set(words(p)), "w_both": set(words(f"{g['name']} {p}"))})
        self.text = " ".join(f"{r['group']} {r['property']}" for r in self.rows).lower()
        self.groups = {(r["entity"], r["group"]) for r in self.rows}

    def best(self, name: str) -> tuple[dict | None, str, float]:
        w = set(words(name))
        if not w:
            return None, "none", 0.0
        cover, near = (None, "none", 0.0), (None, "none", 0.0)
        for r in self.rows:
            if (r["group"] or "") == "General Properties":     # generic, listed by every entity
                continue
            own = set(words(r["entity"])) | set(words(r["group"]))
            for key in ("w_prop", "w_both"):
                R = r[key]
                if not R:
                    continue
                rec, prec = len(w & R) / len(w), len(w & R) / len(R)
                if w == R:
                    return r, "lexical-exact", 1.0
                if len(w) == 1:          # 'Width' only from 'Width' or '<entity/group words> Width'
                    ok = rec == 1.0 and (R - w) <= own
                else:                    # the property set's words may help, but not at 50%
                    ok = rec == 1.0 and (prec >= 0.5 if key == "w_prop" else prec > 0.5)
                if ok:
                    if prec > cover[2]:
                        cover = (r, "lexical-cover", prec)
                elif (rec + prec) / 2 > near[2]:
                    near = (r, "none", (rec + prec) / 2)      # best miss, kept for review
        return cover if cover[0] is not None else near

    def find(self, pred) -> dict | None:
        return next((r for r in self.rows if pred(r)), None)


def evidence(r: dict | None) -> dict | None:
    return {"entity": r["entity"], "group": r["group"], "property": r["property"]} if r else None


def judge(f: dict, rows: Rows, item: dict, spec: dict) -> dict:
    kind = f["facet"]
    out = {"determined": False, "scope": "facet", "method": "none", "evidence": None}
    if kind == "property" and f.get("origin") == "whole_set":
        out["reason"] = "set-level facet (" + (f.get("why_not") or "") + "); the IDM never prohibits or names a set"
        return out
    if kind == "property":
        r, how, score = rows.best(f.get("baseName") or "")
        if not how.startswith("lexical"):
            want = set(READINGS.get(f.get("baseName") or "", []))
            hit = rows.find(lambda x: (x["entity"], x["group"], x["property"]) in want)
            if hit:
                r, how, score = hit, "reading", 1.0
        if how.startswith("lexical") or how == "reading":
            out.update(determined=True, method=how, evidence=evidence(r), score=round(score, 2))
            vals = [v for v in restriction_values(f.get("value")) if v.upper() not in CATCH_ALL]
            if vals:
                missing = [v for v in vals if v.lower() not in rows.text]
                if missing:
                    out.update(scope="value", value_missing=missing[:12])
                    out["determined_value"] = False
                else:
                    out["determined_value"] = True
        else:
            out.update(best_candidate=evidence(r), score=round(score, 2))
        return out
    if kind == "attribute":
        name = (f.get("name") or "")
        if name == "Name":
            r = rows.find(lambda r: r["property"].lower() in ("identification", "name") or
                          r["property"].lower().endswith(" name"))
        elif name == "Description":
            r = rows.find(lambda r: "description" in r["property"].lower())
        elif name in ("ObjectType", "PredefinedType"):
            r = rows.find(lambda r: r["property"].lower() == "type" or (r["group"] or "").lower() in ("type", "types"))
        elif name == "Tag":
            r = rows.find(lambda r: r["property"].lower() == "identification")
        else:
            r = None
        if r:
            out.update(determined=True, method="attribute-rule", evidence=evidence(r))
            if f.get("value") and not all(v.lower() in rows.text for v in restriction_values(f["value"])):
                out.update(scope="value", determined_value=False)
        return out
    if kind == "material":
        r = rows.find(lambda r: "material" in r["property"].lower() or "material" in (r["group"] or "").lower())
        if r:
            out.update(determined=True, method="material-rule", evidence=evidence(r))
        return out
    if kind == "classification":
        r = rows.find(lambda r: "pay item" in (r["group"] or "").lower() or "item number" in r["property"].lower())
        if r:
            out.update(determined=True, method="classification-rule", evidence=evidence(r))
        return out
    if kind == "partOf":
        want = {"4.1.6": "SUPERSTRUCTURE", "4.1.7": "SUBSTRUCTURE"}.get(item.get("idm_section"))
        if want and (f.get("entity") or "").upper() == "IFCBRIDGEPART" and \
                (f.get("entityPredefinedType") or "").upper() == want:
            out.update(determined=True, method="section",
                       evidence={"section": item["idm_section"], "heading": item.get("section_title")})
        return out
    out["reason"] = f"{kind} facet: no IDM row states it"
    return out


def main():
    OUT.mkdir(exist_ok=True)
    items = load(ROOT / "items.jsonl")
    ents = {e["id"]: e for e in load(ROOT / "idm" / "entities.jsonl")}
    sec_title = {e["section"]: e["section_title"] for e in ents.values()}
    specs = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs_expanded.jsonl")}
    # document item: a spec may cite the rows of the IDM entities aligned to it, plus the rows that
    # apply to every element (4.1.2 Contract Information: pay items); not any row anywhere
    import csv
    spec_idm = defaultdict(set)
    with open(ROOT / "alignment.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for sid in (r["ids_spec_ids"] or "").split():
                spec_idm[sid].add(r["idm_id"])
    everywhere = [e for e in ents.values() if e["section"] == "4.1.2"]
    doc_rows = {}
    out, summary = [], {}
    for it in items:
        doc = it["setting"] == "document"
        it = {**it, "section_title": sec_title.get(it.get("idm_section"))}
        for sid in it["reference_spec_ids"]:
            sp = specs[sid]
            if doc:
                if sid not in doc_rows:
                    doc_rows[sid] = Rows([ents[i] for i in sorted(spec_idm[sid])] + everywhere)
                rows = doc_rows[sid]
                secs = {ents[i]["section"] for i in spec_idm[sid]}
                it = {**it, "idm_section": next(iter(secs)) if len(secs) == 1 else None}
            else:
                rows = Rows([ents[it["idm_id"]]])
            for f in sp["requirements"]:
                j = judge(f, rows, it, sp)
                facet = f"{f['facet']} " + (f"{f.get('propertySet')}.{f.get('baseName')}" if f["facet"] == "property"
                                            else str(f.get("name") or f.get("entity") or f.get("system") or f.get("value") or ""))
                row = {"id": it["id"], "spec_id": sid, "req_index": f["req_index"], "facet": facet,
                       "kind": f["facet"], "origin": f.get("origin"), "ref_cardinality": f.get("cardinality"),
                       "value": f.get("value"), **j}
                if j["determined"]:
                    row["idm_cardinality"] = "required"
                    row["cardinality_conflict"] = (f.get("cardinality") or "required") != "required"
                out.append(row)
    with open(OUT / "determinacy.jsonl", "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def count(rs):
        c = Counter()
        for r in rs:
            c["facets"] += 1
            c["determined" if r["determined"] else "undetermined"] += 1
            if r["determined"] and r["scope"] == "value":
                c["determined_value_undetermined"] += 1
            if r.get("cardinality_conflict"):
                c["determined_but_ref_optional"] += 1
        return dict(c)

    ent_rows = [r for r in out if not r["id"].endswith("section4")]
    doc_rows = [r for r in out if r["id"].endswith("section4")]
    summary["entity_items"] = count(ent_rows)
    summary["document_item"] = count(doc_rows)
    summary["entity_items_by_kind"] = {k: count([r for r in ent_rows if r["kind"] == k])
                                       for k in sorted({r["kind"] for r in ent_rows})}
    summary["document_by_kind"] = {k: count([r for r in doc_rows if r["kind"] == k])
                                   for k in sorted({r["kind"] for r in doc_rows})}
    summary["entity_items_by_method"] = dict(Counter(r["method"] for r in ent_rows))
    per_item = defaultdict(lambda: [0, 0])
    for r in ent_rows:
        per_item[r["id"]][0 if r["determined"] else 1] += 1
    summary["entity_items_share_determined"] = {
        "min": min(d / (d + u) for d, u in per_item.values()),
        "median": sorted(d / (d + u) for d, u in per_item.values())[len(per_item) // 2],
        "max": max(d / (d + u) for d, u in per_item.values()),
        "items_with_none_determined": sum(1 for d, u in per_item.values() if d == 0)}
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "determinacy_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
