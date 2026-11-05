"""Step 4 — alignment: IDM-1 entity -> workbook Industry Name -> IFC class.PredefinedType -> IDS spec(s).

    python -X utf8 -m eval.usbridge.align

Part of the answer key. Writes eval/usbridge/alignment.csv (one row per IDM-1 entity x workbook
entity, or IDM-1 entity x IDS-only spec, or an unmatched IDM-1 entity) and
eval/usbridge/summary/alignment_summary.json (counts, unmatched on both sides).

IDM-1 -> workbook, first rule that fires per pair:
  exact       the IDM name equals an Industry Name
  normalised  equal after case / plural / punctuation folding, or the same word set, or one of the
              IDM name's alternatives ("Abutment/ End Bent" -> "Abutment"; "Pier Wall (Crash Wall)"
              -> "Crash Wall") equals an Industry Name, or the IDM name equals the usBridge DD Name
  manual      MANUAL below; every row carries its reason
Workbook -> IDS spec, per workbook entity:
  name        spec name == Industry Name (normalised) and the spec's applicability class is the
              workbook's IFC class
  listed      the Industry Name is one of the alternatives a combined spec name lists
              ("Precast Girder Segment, Girder (Rolled Steel) or Girder Closure Pour")
  applicability  same IFC class and predefinedType (the workbook's USERDEFINED objectType is what
              the IDS writes as predefinedType)
  manual      WB_SPEC_EXTRA (type-object specs, bearings)
"X Predefined Types" specs (class-wide whitelists of allowed predefined types) and the General
specs for resources are reached only through MANUAL or the whole-document item.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"          # committed: counts and totals only
REF = ROOT / "reference"

# IDM-1 entity -> [(workbook Industry Name | "spec:<IDS spec name>", reason)]; "tab=" disambiguates
MANUAL: dict[str, list[tuple[str, str]]] = {
    "Identification": [
        ("Project", "contract/project numbers and project name live in usBrPset_ProjectCommon on IfcProject"),
        ("Girder Bridge", "structure number/name, carried and crossed roadways live in usBrPset_BridgeIdentification, usBrPset_Roadway, usBrPset_FeatureIdentification on IfcBridge"),
        ("Slab Bridge", "same as Girder Bridge, the other IfcBridge type"),
    ],
    "Location": [
        ("Project", "city/county/district/state live in usBrPset_ProjectLocation on IfcProject"),
        ("Girder Bridge", "latitude/longitude live in usBrPset_BridgeIdentification (RefLatitude/RefLongitude)"),
        ("Slab Bridge", "same as Girder Bridge"),
    ],
    "Metadata": [
        ("Project", "model version, preparation date, approval status live in usBrPset_ProjectCommon"),
        ("spec:Geospatial", "coordinate systems and reference frames become IfcProjectedCRS (General spec)"),
        ("Designer\nChecker\nEngineer of Record\nProject Manager", "associated stakeholders become IfcPerson"),
        ("Owner Agency\nDesign Agency\nContractor", "associated stakeholders become IfcOrganization"),
        ("Actor", "associated stakeholders are attached through IfcActor"),
        ("Project Role", "stakeholder roles become IfcActorRole"),
    ],
    "Project Descriptions": [
        ("Project", "letting date and project description live in usBrPset_ProjectCommon"),
        ("Girder Bridge", "traffic (AADT/AADTT), hydraulic data, design loading live in usBridge psets on IfcBridge"),
        ("Slab Bridge", "same as Girder Bridge"),
        ("Construction Specifications", "construction specifications become an IfcDocumentReference"),
        ("Design Specifications", "design specifications become an IfcDocumentReference"),
    ],
    "Contract Information": [
        ("Pay Item Specification", "pay item information becomes an IfcClassification (pay item specification)"),
        ("Pay Item", "each pay item becomes an IfcClassificationReference"),
    ],
    "Horizontal Alignment": [
        ("spec:Alignment", "horizontal alignment is part of IfcAlignment (General spec)"),
        ("spec:Alignment - Horizontal", "IfcAlignmentHorizontal"),
        ("spec:Alignment - Horizontal Segments", "IfcAlignmentHorizontalSegment"),
    ],
    "Vertical Profile": [
        ("spec:Alignment", "vertical profile is part of IfcAlignment (General spec)"),
        ("spec:Alignment - Vertical", "IfcAlignmentVertical"),
        ("spec:Alignment - Vertical Segments", "IfcAlignmentVerticalSegment"),
    ],
    "Bridge Configuration": [
        ("Girder Bridge", "bridge length, number of spans, clearances live in usBrPset_BridgeGeometry / usBrPset_Roadway on IfcBridge"),
        ("Slab Bridge", "same as Girder Bridge"),
    ],
    "Bridge Control Information": [
        ("Girder Bridge", "begin/end stations and skew live in usBrPset_BridgeGeometry"),
        ("Slab Bridge", "same as Girder Bridge"),
        ("tab=IfcBridgePart|Abutment", "stations/skew at abutment centerline live in usBrPset_SubstructureCommon"),
        ("tab=IfcBridgePart|Pier", "stations/skew at pier centerline live in usBrPset_SubstructureCommon"),
    ],
    "Deck": [
        ("Deck Slab", "the deck's slab (IfcSlab.FLOOR) carries thickness, form type, pour data"),
        ("Closure Pour", "the IDM's Closure Pour group"),
        ("Wearing Surface", "the IDM's Overlay/Wearing Surface group"),
    ],
    "Bearing": [
        ("Bearing Plate", "IDM bearing types Masonry/Sole/Top/Bottom Plate"),
        ("Anchor Bolt", "IDM's Anchor Bolt group"),
    ],
    "Abutment/ End Bent": [
        ("Backwall", "IDM feature Back Wall"),
        ("Stem Wall", "IDM feature Stem Wall/Breast Wall"),
    ],
    "Wingwall/ Stem Wall": [("Backfill", "IDM's Backfill Properties group")],
    "Deck Joints": [("Expansion Joint", "deck joint types (compression seal, modular, strip seal, finger) are expansion joint devices")],
    "Girder": [
        ("Non-Spliced Prestressed Concrete Girder", "IDM's Precast/Prestressed Concrete Girder group"),
        ("Precast Girder Segment", "precast girder segments (spliced concrete girders)"),
        ("Girder Closure Pour", "closure pours of spliced concrete girders"),
        ("Girder (Rolled Steel)", "IDM's steel girder groups"),
        ("Girders (Rolled Steel)", "IDM's steel girder groups (assembly)"),
        ("Girders (Built-up Steel)", "IDM's steel girder groups (assembly)"),
        ("Girder Segment (Built-up Steel)", "IDM's steel girder groups (segment)"),
        ("Girders (Post-Tensioned Spliced Concrete)", "IDM's spliced concrete girders (assembly)"),
        ("Flange Plate", "IDM's Steel Girder Flange Properties group"),
        ("Web Plate", "IDM's Steel Girder Web Properties group"),
    ],
    "Railing": [
        ("Guardrail", "railing types in IFC: IfcRailing.GUARDRAIL"),
        ("Handrail", "IDM's Handrailing feature: IfcRailing.HANDRAIL"),
        ("Fence", "IfcRailing.FENCE"),
    ],
    "Transverse Member": [
        ("Cross-Frames", "IDM type Cross Frame"),
        ("Cross-Frame Member", "members of a cross frame"),
        ("Diaphragm (Steel)", "IDM type Diaphragm (steel)"),
        ("Steel Diaphragm Member", "members of a steel diaphragm"),
        ("Concrete Diaphragm", "IDM type Diaphragm (concrete)"),
    ],
    "Drilled Shaft": [("Rock Socket", "IDM's Rock Socket group")],
    "Footing/Pile Cap/Drilled Shaft Cap": [
        ("Spread Footing", "IDM's Spread Footing Properties group"),
        ("Strip Footing", "footing"),
        ("Drilled Footing", "drilled shaft cap / drilled footing"),
    ],
    "Pile": [
        ("Driven Pile", "the IDM's pile (drilled shafts are their own IDM entity)"),
        ("Pile Sleeve", "IDM's Pile Sleeve group"),
        ("Drilled Hole / Prebored Hole", "IDM's Prebore group"),
        ("Rock Socket", "IDM's Rock Socket group"),
    ],
    "Slope Protection": [
        ("Slope Protection Surface", "IDM type Concrete (slope paving)"),
        ("Riprap", "IDM types Riprap, Grouted Riprap"),
    ],
    "Bolt Assembly": [("Bolt", "bolt assembly = IfcMechanicalFastener.BOLT (DD name BoltAssembly)")],
    "Drainage System": [
        ("Distribution System", "drainage system = IfcDistributionSystem"),
        ("Rigid Pipe", "drainage element"), ("Flexible Pipe", "drainage element"),
        ("Pipe Fittings", "drainage element"), ("Drain / Inlet", "drainage element"),
    ],
    "Feature": [
        ("Hole", "IDM's Bolt Hole / Slotted Hole / Opening groups"),
        ("tab=IfcVirtualElement|Keyway", "IDM's Keyway group (void)"),
        ("tab=IfcProjectionElement|Keyway", "IDM's Keyway group (projection)"),
    ],
    "Gusset": [("Gusset Plate", "the IDM omits 'Plate'")],
    "Stiffener": [("Stiffener Plate", "the IDM omits 'Plate'")],
    "Drill and Bond Chemical Adhesive Anchor": [("Anchor Bolt", "usBrPset_AnchorBolt.AnchorType covers Chemical_Epoxy")],
    "Drill and Bond Dowel Bar": [("Dowel Bar", "drilled-and-bonded dowel = IfcReinforcingBar.DOWEL")],
    "Longitudinal Bar": [("Reinforcing Bar", "longitudinal bars are reinforcing bars")],
    "Transverse Reinforcement": [("Reinforcing Bar", "transverse bars are reinforcing bars")],
    "Structural Component Reinforcement": [
        ("Reinforcing Bar", "bar marks, shapes, cover"),
        ("Reinforcement Cage", "assembled reinforcement"),
        ("Welded-Wire Reinforcement", "mesh reinforcement"),
    ],
    "Post-Tensioning": [
        ("Tendon", "post-tensioning tendons"),
        ("Tendon Conduit & Accessories", "IDM's ducts and grout"),
        ("Tendon Anchorage", "IDM's Post-Tensioning Hardware (anchorage)"),
        ("Prestressing / Post-tensioning Tendon Assembly", "tendon assembly"),
        ("Prestressing / Post-tensioning Tendon Assembly Bundle", "tendon bundle"),
    ],
    "Prestressing": [
        ("Tendon", "prestressing strands"),
        ("Prestressing / Post-tensioning Tendon Assembly", "tendon assembly"),
    ],
    "Coating": [("Surface Treatment", "coatings become IfcSurfaceFeature.TREATMENT with usBrPset_Coating")],
    "Deck Placement": [("Deck Slab", "pour stages and placements live in usBrPset_ConcretePour on the deck slab")],
    "Structure": [
        ("Culverts", "buried structure = culvert (IfcBridgePart)"),
        ("tab=IfcFacilityPartCommon|Culvert", "buried structure = culvert (IfcFacilityPartCommon)"),
        ("tab=IfcBridgePart|Culvert Barrel", "IDM types Box Culvert / Arch / Three-Sided"),
        ("Culvert Top Slab", "IDM feature Top Slab"), ("Culvert Bottom Slab", "IDM feature Bottom Slab"),
        ("Culvert Wall", "IDM features Exterior/Interior Wall"), ("Headwall", "IDM feature Headwall/Parapet"),
        ("Precast Segments (Culvert)", "precast culvert units"),
    ],
    "Mechanically Stabilized Earth (MSE) Walls": [
        ("Precast Wall Panel", "IDM feature Facing (panels)"),
        ("Reinforcing Strap", "IDM feature Strap Zone"),
        ("Geosynthetic Reinforcement", "MSE reinforcement"),
        ("Coping", "IDM feature Coping"),
        ("tab=IfcWall|Facing", "IDM feature Facing"),
        ("Backfill", "IDM's Backfill Properties group"),
    ],
    "Reinforced Concrete Retaining Wall": [
        ("Cast-In-Place Wall", "reinforced concrete retaining wall = IfcWall.RETAININGWALL, cast-in-place"),
        ("Precast Tilt-up Wall (Simple)", "IDM type Precast"),
        ("Coping", "IDM's Coping group"),
        ("Backfill", "IDM's Backfill Properties group"),
    ],
    "Soil Nail Wall": [
        ("tab=IfcElementAssembly_Anchoring|Soil Nail", "soil nail assembly"),
        ("tab=IfcMember|Soil Nail", "soil nail bar"),
        ("tab=IfcWall|Facing", "IDM's Facing group"),
        ("Shotcrete Wall", "soil nail walls are faced with shotcrete"),
        ("Coping", "IDM's Coping group"),
        ("Backfill", "IDM's Backfill Properties group"),
    ],
    "Soldier Pile Wall": [
        ("Lagging", "soldier pile wall lagging"),
        ("Waler", "soldier pile wall waler"),
        ("Coping", "IDM feature Coping"),
        ("Driven Pile", "IDM's Pile group (the soldier piles)"),
        ("Backfill", "IDM's Backfill Properties group"),
    ],
}
# IDM-1 entities with nothing in the workbook or the IDS; the reason is the answer
UNMATCHED_REASON = {
    "Cross Section": "roadway cross-section (lanes, shoulders, slopes) has no usBridge entity or IDS spec",
    "Architectural Feature": "no usBridge class for an architectural feature; aesthetics became usBrPset_Wall.AestheticType",
    "Seal Coat/ Tremie Seal/Seal Slab": "no usBridge class for a seal coat",
    "Bent Plate": "no bent-plate class; bending became usBrPset_PlateCommon on every plate",
    "Field Splice": "no field-splice class; its components (bolts, fill and splice plates) are their own IDM entities",
    "Weld": "no usBridge class for a weld",
    "Accessories": "no usBridge class for chairs, standees, support bars",
    "Environmental": "noise and nesting/spawning restrictions have no usBridge property",
    "Miscellaneous": "temporary shoring has no usBridge class",
}
# workbook entity -> extra IDS spec names (type objects, generic bearings)
WB_SPEC_EXTRA = {
    "Bearing": ["Bearing (Generic)", "Elastomeric Bearing"],
    "Reinforcing Bar": ["Reinforcing Bar Type"],
    "Dowel Bar": ["Dowel Bar Type"],
    "Welded-Wire Reinforcement": ["Reinforcing Mesh", "Reinforcing Mesh Type"],
    "Tendon": ["Tendon Type"],
    "Tendon Conduit & Accessories": ["Tendon Conduit"],
    "Pipe Fittings": ["Pipe Fitting"],
    "Project Control Point / / Benchmark": ["Project Control Point / Benchmark"],
}


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def singular(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def norm(s: str | None) -> str:
    toks = re.findall(r"[a-z0-9]+", (s or "").lower())
    return " ".join(singular(t) for t in toks)


def tokset(s: str | None) -> frozenset:
    return frozenset(norm(s).split())


def alternatives(name: str) -> list[str]:
    """'Abutment/ End Bent' -> ['Abutment', 'End Bent']; 'Pier Wall (Crash Wall)' -> ['Pier Wall', 'Crash Wall']."""
    out = []
    paren = re.findall(r"\(([^)]*)\)", name)
    bare = re.sub(r"\s*\([^)]*\)", "", name).strip()
    for part in re.split(r"\s*/\s*", bare):
        if part:
            out.append(part.strip())
    out += [p.strip() for p in paren if p.strip()]
    return [a for a in out if a and a != name]


def spec_alternatives(name: str) -> list[str]:
    return [p.strip() for p in re.split(r",\s*|\s+or\s+|\s*&\s*", name) if p.strip()]


def entities_of(applies_to: dict | None) -> set[str]:
    """IFC classes an applicability admits: 'IFCWALL' or RESTRICTION(enumeration=A,enumeration=B)."""
    v = (applies_to or {}).get("entity") or ""
    return set(re.findall(r"enumeration=([A-Z0-9_]+)", v)) if v.startswith("RESTRICTION(") else {v}


def wb_key(e: dict) -> str:
    return f"{e['tab']}|{e['industry_name']}"


def main():
    idm = load(ROOT / "idm" / "entities.jsonl")
    wb = load(REF / "workbook_entities.jsonl")
    specs = [s for s in load(REF / "specs.jsonl") if s["file"] != "usBrSpec_PropertySets.ids"]
    by_name = defaultdict(list)
    for s in specs:
        by_name[norm(s["name"])].append(s)

    # ---------------------------------------------------------------- workbook -> IDS
    wb_specs: dict[str, list[tuple[dict, str]]] = {}
    for e in wb:
        ent = (e["ifc"].get("entity") or "").upper()
        pt = (e["ifc"].get("objectType") or e["ifc"].get("predefinedType") or "").upper()
        found = []
        for s in by_name.get(norm(e["industry_name"]), []):
            if ent in entities_of(s["applies_to"]) or not ent:
                found.append((s, "name"))
        if not found:
            for s in specs:
                if e["industry_name"] in spec_alternatives(s["name"]) and len(spec_alternatives(s["name"])) > 1 \
                        and ent in entities_of(s["applies_to"]):
                    found.append((s, "listed"))
        if not found and ent and not e["ifc"].get("predefinedType_any"):
            for s in specs:          # same class and predefinedType; both empty counts (IfcPerson)
                a = s["applies_to"] or {}
                if ent in entities_of(a) and (a.get("predefinedType") or "").upper() == pt \
                        and not s["name"].endswith("Predefined Types"):
                    found.append((s, "applicability"))
        for extra in WB_SPEC_EXTRA.get(e["industry_name"], []):
            for s in by_name.get(norm(extra), []):
                if all(s is not f[0] for f in found):
                    found.append((s, "manual"))
        wb_specs[wb_key(e)] = found

    # ---------------------------------------------------------------- IDM -> workbook
    def find_wb(target: str) -> list[dict]:
        if target.startswith("tab="):
            tab, name = target[4:].split("|", 1)
            return [e for e in wb if e["tab"] == tab and same(e, name)]
        return [e for e in wb if same(e, target)]

    def same(e: dict, name: str) -> bool:
        return name in (e["industry_name"], e["industry_name"].replace("\n", " / "))

    rows, idm_hits = [], defaultdict(list)
    for d in idm:
        name, links = d["entity"], []
        for e in wb:
            names = [e["industry_name"]] + e["industry_names"]
            if name in names:
                links.append((e, "exact", "IDM name = Industry Name"))
                continue
            how = None
            if any(norm(name) == norm(n) for n in names):
                how = "case/plural/punctuation"
            elif any(tokset(name) == tokset(n) for n in names):
                how = "same words, other order"
            else:
                alt = next((a for a in alternatives(name) if any(norm(a) == norm(n) for n in names)), None)
                if alt:
                    how = f"IDM alternative name '{alt}'"
                elif e.get("dd_name") and norm(name).replace(" ", "") == norm(e["dd_name"]).replace(" ", ""):
                    how = f"IDM name = usBridge DD Name '{e['dd_name']}'"
            if how:
                links.append((e, "normalised", how))
        for target, reason in MANUAL.get(name, []):
            if target.startswith("spec:"):
                for s in by_name.get(norm(target[5:]), []):
                    links.append(({"spec_only": s}, "manual", reason))
                continue
            hits = find_wb(target)
            if not hits:
                raise SystemExit(f"MANUAL target not in workbook: {name} -> {target!r}")
            for e in hits:
                if all(not (l[0] is e) for l in links):
                    links.append((e, "manual", reason))
        if not links:
            rows.append({"idm_id": d["id"], "idm_entity": name, "idm_section": d["section"],
                         "idm_wb_match": "unmatched", "reason": UNMATCHED_REASON.get(name, "")})
            continue
        if name in UNMATCHED_REASON:
            raise SystemExit(f"{name} is matched and also listed as unmatched")
        for e, how, reason in links:
            if "spec_only" in e:
                s = e["spec_only"]
                specs_here = [(s, "manual")]
                base = {"wb_tab": "", "wb_industry_name": "", "wb_dd_name": "",
                        "ifc_class": (s["applies_to"] or {}).get("entity", ""),
                        "ifc_predefined_type": (s["applies_to"] or {}).get("predefinedType", ""),
                        "ifc_object_type": ""}
            else:
                specs_here = wb_specs[wb_key(e)]
                base = {"wb_tab": e["tab"], "wb_industry_name": e["industry_name"].replace("\n", " / "),
                        "wb_dd_name": e.get("dd_name") or "", "ifc_class": e["ifc"].get("entity", ""),
                        "ifc_predefined_type": e["ifc"].get("predefinedType", "") or
                                               ("(any)" if e["ifc"].get("predefinedType_any") else ""),
                        "ifc_object_type": e["ifc"].get("objectType", "")}
                idm_hits[wb_key(e)].append(d["id"])
            rows.append({"idm_id": d["id"], "idm_entity": name, "idm_section": d["section"], **base,
                         "ids_spec_ids": " ".join(s["spec_id"] for s, _ in specs_here),
                         "ids_spec_names": " | ".join(s["name"] for s, _ in specs_here),
                         "wb_ids_match": " ".join(sorted({m for _, m in specs_here})) or "none",
                         "idm_wb_match": how, "reason": reason})

    cols = ["idm_id", "idm_entity", "idm_section", "wb_tab", "wb_industry_name", "wb_dd_name", "ifc_class",
            "ifc_predefined_type", "ifc_object_type", "ids_spec_ids", "ids_spec_names", "idm_wb_match",
            "wb_ids_match", "reason"]
    with open(ROOT / "alignment.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    # ---------------------------------------------------------------- summary
    reached_specs = {sid for r in rows for sid in (r.get("ids_spec_ids") or "").split()}
    best = {}
    for r in rows:
        order = {"exact": 0, "normalised": 1, "manual": 2, "unmatched": 3}
        k = r["idm_id"]
        if k not in best or order[r["idm_wb_match"]] < order[best[k]]:
            best[k] = r["idm_wb_match"]
    idm_specs = defaultdict(set)
    for r in rows:
        idm_specs[r["idm_id"]] |= set((r.get("ids_spec_ids") or "").split())
    summary = {
        "idm_entities": len(idm),
        "idm_by_best_match": {k: sum(1 for v in best.values() if v == k) for k in ("exact", "normalised", "manual", "unmatched")},
        "idm_aligned": sum(1 for v in best.values() if v != "unmatched"),
        "idm_aligned_with_ids_spec": sum(1 for d in idm if idm_specs[d["id"]]),
        "idm_aligned_without_ids_spec": [d["entity"] for d in idm if best[d["id"]] != "unmatched" and not idm_specs[d["id"]]],
        "alignment_rows": len(rows),
        "rows_by_match": {k: sum(1 for r in rows if r["idm_wb_match"] == k) for k in ("exact", "normalised", "manual", "unmatched")},
        "idm_unmatched": [{"entity": r["idm_entity"], "reason": r["reason"]} for r in rows if r["idm_wb_match"] == "unmatched"],
        "workbook_entities": len(wb),
        "workbook_reached": sum(1 for e in wb if idm_hits.get(wb_key(e))),
        "workbook_unreached": [{"tab": e["tab"], "industry_name": e["industry_name"].replace("\n", " / "),
                                "ifc": e["ifc_name"]} for e in wb if not idm_hits.get(wb_key(e))],
        "workbook_without_ids_spec": [e["industry_name"].replace("\n", " / ") for e in wb if not wb_specs[wb_key(e)]],
        "ids_specs": len(specs),
        "ids_specs_reached": len(reached_specs),
        "ids_specs_unreached": [{"spec_id": s["spec_id"], "name": s["name"], "applies_to": s["applies_to"]}
                                for s in specs if s["spec_id"] not in reached_specs],
    }
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "alignment_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if not isinstance(v, list)}, indent=1))
    print("idm unmatched:", [x["entity"] for x in summary["idm_unmatched"]])
    print("idm aligned but no IDS spec:", summary["idm_aligned_without_ids_spec"])
    print("workbook unreached:", len(summary["workbook_unreached"]), "| ids specs unreached:", len(summary["ids_specs_unreached"]))


if __name__ == "__main__":
    main()
