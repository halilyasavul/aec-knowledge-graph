"""Applicability determinacy: does the IDM-1 request state each reference spec's predefined type?

    python -X utf8 -m eval.usbridge.applicability

Written after the v10b pilot (new file, as the scoring plan requires; the pilot is reported with
and without it). Writes annotations/applicability.jsonl (one row per item x reference spec with a
predefined type) and summary/applicability_summary.json.

Rule, per item:
  - a spec whose IFC entity has no other typed spec in the item: determined. Mapping the IDM
    entity to that IFC kind (Pier Cap -> IFCBEAM PIERCAP) is the schema knowledge under test.
  - specs that share an IFC entity with different predefined types (siblings: Girder Bridge /
    Slab Bridge for one IDM table): determined only where the IDM names that kind, by its entity
    name or by a property group of its own (Deck: "Closure Pour" group -> CLOSURE_POUR). Types or
    features listed as values in a property column (Bearing "Types: Elastomeric, Pot, ...") do not
    count: they are values of the one element the table describes. Each sibling decision is a
    reading below, with its reason.
  - whole-document item: a spec's type is determined if any entity item aligned to it determines it.
Machine-assisted readings by the annotator (Claude, 2026-11-04); not reviewed by a human.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"

# (item id, IFC entity, predefined type) -> (determined, reason); sibling groups only
READINGS: dict[tuple[str, str, str], tuple[bool, str]] = {}


def _r(items, entity, ptypes, determined, reason):
    for i in items:
        for p in ptypes:
            READINGS[(i, entity, p)] = (determined, reason)


_r(["usb-idm1-001", "usb-idm1-002", "usb-idm1-004", "usb-idm1-009", "usb-idm1-010"], "IFCBRIDGE",
   ["GIRDER", "SLAB_BRIDGE"], False, "the IDM table is about the bridge; it never says girder or slab bridge")
_r(["usb-idm1-010"], "IFCBRIDGEPART", ["ABUTMENT", "PIER"], False,
   "abutment and pier appear only inside station property names; no group of their own")
_r(["usb-idm1-013"], "IFCBEARING",
   ["RESTRICTION(enumeration=USERDEFINED,enumeration=CYLINDRICAL,enumeration=DISK,enumeration=GUIDE,"
    "enumeration=POT,enumeration=ROCKER,enumeration=ROLLER,enumeration=SPHERICAL)", "ELASTOMERIC"], False,
   "one table for all bearings; Elastomeric, Pot, ... are values of its Types group")
_r(["usb-idm1-015"], "IFCSLAB", ["FLOOR"], True, "the IDM entity is the deck")
_r(["usb-idm1-015"], "IFCSLAB", ["CLOSURE_POUR"], True, "property group 'Closure Pour'")
_r(["usb-idm1-015"], "IFCSLAB", ["WEARING"], True, "property group 'Overlay/Wearing Surface'")
_r(["usb-idm1-019"], "IFCBEAM", ["BEAM", "GIRDER_SEGMENT"], False,
   "'Precast/Prestressed Concrete Girder' does not separate non-spliced girders from precast segments, "
   "and HDR's GIRDER_SEGMENT spec also covers rolled steel girders")
_r(["usb-idm1-019"], "IFCELEMENTASSEMBLY", ["GIRDER"], True, "the IDM entity is the girder")
_r(["usb-idm1-019"], "IFCELEMENTASSEMBLY", ["GIRDER_SEGMENT"], False, "built-up steel segments are not named")
_r(["usb-idm1-019"], "IFCPLATE", ["FLANGE_PLATE"], True, "property group 'Steel Girder Flange Properties'")
_r(["usb-idm1-019"], "IFCPLATE", ["WEB_PLATE"], True, "property group 'Steel Girder Web Properties'")
_r(["usb-idm1-022"], "IFCRAILING", ["GUARDRAIL", "HANDRAIL", "FENCE"], False,
   "one table for all railings; Handrailing is a value of its Features group")
_r(["usb-idm1-025"], "IFCELEMENTASSEMBLY", ["CROSS_BRACING", "DIAPHRAGM"], False,
   "Cross Frame and Diaphragm are values of the Type group of one transverse-member table")
_r(["usb-idm1-026"], "IFCWALL", ["BACKWALL", "STEM_WALL"], False,
   "Back Wall and Stem Wall/Breast Wall are values of the abutment's Features group")
_r(["usb-idm1-028"], "IFCPILE", ["BORED"], True, "the IDM entity is the drilled shaft")
_r(["usb-idm1-028"], "IFCPILE", ["ROCK_SOCKET"], True, "property group 'Rock Socket'")
_r(["usb-idm1-029"], "IFCFOOTING", ["PILE_CAP"], True, "named in the IDM entity (Footing/Pile Cap/Drilled Shaft Cap)")
_r(["usb-idm1-029"], "IFCFOOTING", ["PAD_FOOTING"], True, "property group 'Spread Footing Properties'")
_r(["usb-idm1-029"], "IFCFOOTING", ["STRIP_FOOTING"], False, "strip footings are not named")
_r(["usb-idm1-029"], "IFCFOOTING", ["DRILLED_FOOTING"], True, "named in the IDM entity (Drilled Shaft Cap)")
_r(["usb-idm1-035"], "IFCWALL", ["PIER_WALL", "CRASH_WALL"], True, "both named in the IDM entity (Pier Wall (Crash Wall))")
_r(["usb-idm1-036"], "IFCPILE", ["DRIVEN"], False, "the IDM says pile; driven is not named")
_r(["usb-idm1-036"], "IFCPILE", ["ROCK_SOCKET"], True, "property group 'Rock Socket'")
_r(["usb-idm1-039"], "IFCWALL", ["STEM_WALL", "WINGWALL"], True, "both named in the IDM entity (Wingwall/ Stem Wall)")
_r(["usb-idm1-044"], "IFCPIPESEGMENT", ["RIGIDSEGMENT", "FLEXIBLESEGMENT"], False,
   "one 'Drainage Element' group; rigid and flexible pipes are not named")
_r(["usb-idm1-049"], "IFCMECHANICALFASTENER", ["SHEARCONNECTOR", "STUDSHEARCONNECTOR"], True,
   "the IDM entity is Shear Connector (Stud)")
_r(["usb-idm1-057"], "IFCELEMENTASSEMBLY", ["TENDON_ASSEMBLY", "TENDON_BUNDLE"], False,
   "tendon assembly and bundle are not named")
_r(["usb-idm1-065"], "IFCSLAB", ["TOPSLAB", "BASESLAB"], False, "Top Slab and Bottom Slab are values of 'Element Features'")
_r(["usb-idm1-065"], "IFCWALL", ["CULVERT_WALL", "HEADWALL"], False,
   "Exterior/Interior Wall and Headwall/Parapet are values of 'Element Features'")
_r(["usb-idm1-066"], "IFCMEMBER", ["PRECASTWALLPANEL", "REINFORCING_STRAP", "GEOSYNTHETIC_REINFORCEMENT"], False,
   "Facing and Strap Zone are values of the Features group")
_r(["usb-idm1-068"], "IFCWALL", ["FACING"], True, "property group 'Facing'")
_r(["usb-idm1-068"], "IFCWALL", ["RETAININGWALL"], True, "the IDM entity is the (soil nail) retaining wall")
_r(["usb-idm1-069"], "IFCMEMBER", ["LAGGING", "WALER"], False, "Lagging is a value of the Features group; waler is not named")


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def main():
    items = load(ROOT / "items.jsonl")
    specs = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs.jsonl")}
    rows, by_spec, missing = [], defaultdict(list), []
    for it in items:
        if it["setting"] != "entity":
            continue
        typed = [(sid, specs[sid]["applies_to"] or {}) for sid in it["reference_spec_ids"]]
        typed = [(sid, a) for sid, a in typed if a.get("predefinedType")]
        per_ent = Counter(a.get("entity") for _, a in typed)
        for sid, a in typed:
            key = (it["id"], a.get("entity"), a.get("predefinedType"))
            if per_ent[a.get("entity")] == 1:
                det, why = True, "the only typed spec of its entity in the item: mapping is the knowledge under test"
            elif key in READINGS:
                det, why = READINGS[key]
            else:
                missing.append(key)
                continue
            rows.append({"id": it["id"], "spec_id": sid, "entity": a.get("entity"),
                         "predefinedType": a.get("predefinedType"), "determined": det, "reason": why})
            by_spec[sid].append(det)
    if missing:
        raise SystemExit(f"sibling specs without a reading: {missing}")
    unused = set(READINGS) - {(r["id"], r["entity"], r["predefinedType"]) for r in rows}
    if unused:
        raise SystemExit(f"readings that match nothing: {sorted(unused)[:5]}")
    doc = next(i for i in items if i["setting"] == "document")
    for sid in doc["reference_spec_ids"]:
        a = specs[sid]["applies_to"] or {}
        if not a.get("predefinedType"):
            continue
        det = any(by_spec.get(sid, []))
        rows.append({"id": doc["id"], "spec_id": sid, "entity": a.get("entity"), "predefinedType": a.get("predefinedType"),
                     "determined": det, "reason": "determined in an aligned entity item" if det
                     else ("undetermined in every aligned entity item" if sid in by_spec else "no IDM-1 entity aligned")})
    (ROOT / "annotations").mkdir(exist_ok=True)
    with open(ROOT / "annotations" / "applicability.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    ent = [r for r in rows if r["id"] != doc["id"]]
    out = {"entity_items": {"typed_specs": len(ent), "determined": sum(r["determined"] for r in ent),
                            "undetermined": sum(not r["determined"] for r in ent),
                            "items_with_undetermined": len({r["id"] for r in ent if not r["determined"]}),
                            "readings": len(READINGS)},
           "document_item": {"typed_specs": len(rows) - len(ent),
                             "determined": sum(r["determined"] for r in rows if r["id"] == doc["id"])}}
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "applicability_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
