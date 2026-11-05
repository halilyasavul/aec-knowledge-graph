"""Step 2 — the usBridge Data Dictionary Workbook 2.0 (IDM 2.0 Appendix 3) and its bSDD twin.

    python -X utf8 -m eval.usbridge.workbook            (needs eval.usbridge.bsdd run once)

Writes
  eval/usbridge/reference/workbook_entities.jsonl  one row per Industry Name in an entity tab: tab,
      block, Industry Name, IFC Name (+ parsed class / predefinedType / objectType), usBridge DD
      Name, Description, the block's attributes (name, data type, IDS cardinality, instructions)
      and property sets (name, the set's "(Applies only to …)" note, source ifc|usbridge,
      properties with cardinality, data type, property type, enumeration, example)
  eval/usbridge/reference/concepts.jsonl  the "US B&S Concepts" hierarchy: concept, depth, path,
      IFC 4.3.2.0 mapping(s) (an "or" row adds an alternative to the concept above), DD name, note
  eval/usbridge/reference/workbook_vs_bsdd.json  differences against the bSDD usBridge dictionary
                                               (summary/workbook_vs_bsdd.json: the counts)

Columns are found by header text, not position: entity blocks differ (some have no DD Name).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"          # committed: counts and totals only
WB = ROOT / "source" / "usBridge_Data_Dictionary_Workbook_Version_2.0.xlsx"
OUT = ROOT / "reference"
SECTIONS = {"Entity": "entity", "IFC Attributes": "attributes",
            "IFC Property Sets and Properties": "ifc_psets",
            "usBridge Property Sets and Properties": "usbridge_psets"}
CARD = {"required": "required", "optional": "optional", "not required": "not_required",
        "prohibited": "prohibited"}


def clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).replace("\r", "").strip()
    return s if s and s not in ("0", "None") else (None if s in ("", "0", "None") else s)


def parse_ifc_name(s: str | None) -> dict:
    """'IfcBeam.Beam' -> IFCBEAM/BEAM; 'IfcSlab.USERDEFINED:HAUNCH' -> USERDEFINED + objectType;
    'IfcMember.PredefinedType' -> any predefined type; trailing ' or' dropped."""
    if not s:
        return {}
    s = re.sub(r"\s+or\s*$", "", s.replace("\n", "").strip())
    m = re.match(r"(Ifc\w+)(?:\.\s*([\w:]+(?: Type)?))?", s)
    if not m:
        return {"raw": s}
    ent, pt = m.group(1), m.group(2)
    if not _is_entity(ent):              # the workbook drops the dot: IfcMechanicalFastenerSHEARCONNECTOR
        cut = next((k for k in range(len(ent) - 1, 3, -1) if _is_entity(ent[:k])), None)
        if cut is None:
            return {"raw": s}
        rest = s[cut:]
        ent = ent[:cut]
        m2 = re.match(r"[A-Z_]+(?::\w+)?", rest)
        pt = pt or (m2.group(0) if m2 else None)
    out = {"entity": ent.upper()}
    if pt and pt.replace(" ", "").lower() == "predefinedtype":
        pt = "PredefinedType"
    if pt and pt.lower() != "predefinedtype":
        if ":" in pt:
            pt, ot = pt.split(":", 1)
            out["objectType"] = ot
        out["predefinedType"] = pt.upper()
    elif pt:
        out["predefinedType_any"] = True
    return out


def _is_entity(name: str) -> bool:
    import ifcopenshell.ifcopenshell_wrapper as W
    try:
        return isinstance(W.schema_by_name("IFC4X3_ADD2").declaration_by_name(name), W.entity)
    except Exception:
        return False


def split_enum(v: str | None) -> list[str] | None:
    if not v:
        return None
    sep = r"[\n;]" if re.search(r"[\n;]", v) else r","        # "Primary, Secondary" too
    parts = [p.strip() for p in re.split(sep, v) if p.strip()]
    return parts or None


def parse_tab(ws) -> list[dict]:
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    blocks, cur, sec, header, pset = [], None, None, None, None
    for i, r in enumerate(rows, 1):
        b = clean(r[1]) if len(r) > 1 else None
        if b in SECTIONS:
            sec, header = SECTIONS[b], None
            if sec == "entity":
                cur = {"entities": [], "attributes": [], "psets": [], "first_row": i}
                blocks.append(cur)
            continue
        if cur is None or not any(clean(c) for c in r):
            continue
        if header is None:                     # the row after a section marker is its header
            header = {clean(c): j for j, c in enumerate(r) if clean(c)}
            continue
        col = lambda name: clean(r[header[name]]) if name in header and header[name] < len(r) else None
        if sec == "entity":
            if not col("Industry Name") and not col("IFC Name"):
                continue
            cur["entities"].append({"industry_name": col("Industry Name"), "ifc_name": col("IFC Name"),
                                    "dd_name": col("usBridge DD Name"), "description": col("Description"),
                                    "row": i})
        elif sec == "attributes":
            if col("Name") in (None, "None"):
                continue
            cur["attributes"].append({"name": col("Name"), "data_type": col("Data Type"),
                                      "cardinality": CARD.get((col("IDS Cardinality") or "").lower(),
                                                              col("IDS Cardinality")),
                                      "instructions": col("Instructions"), "row": i})
        elif sec in ("ifc_psets", "usbridge_psets"):
            name_cell = col("Property Set Name")
            prop = col("Property Name")
            if name_cell and name_cell.lower() == "none" or (name_cell is None and prop is None):
                continue
            if name_cell and not prop and name_cell.startswith("*"):
                continue                       # a footnote under the table
            if name_cell:
                first, _, note = name_cell.partition("\n")
                pset = {"pset": first.strip().rstrip("*"), "note": note.strip() or None,
                        "footnote_mark": first.strip().endswith("*"),
                        "source": "ifc" if sec == "ifc_psets" else "usbridge", "properties": []}
                cur["psets"].append(pset)
            if prop and pset is not None:
                pset["properties"].append({
                    "name": prop,
                    "cardinality": CARD.get((col("IDS Cardinality") or "").lower(), col("IDS Cardinality")),
                    "description": col("Description"), "data_type": col("Data Type"),
                    "property_type": col("PropertyType"), "enumeration": split_enum(col("Enumeration")),
                    "example": col("Example"), "row": i})
    return blocks


def note_targets(note: str | None) -> list[str] | None:
    """'(Applies only to Deck Slab, Wearing Surface, and Approach Slab)' -> the three names;
    None when the set has no such note (it applies to every entity of the block)."""
    if not note:
        return None
    m = re.search(r"(?:only applies|applies only|appies only|applies)\s+to\s+(.+)", note.replace("\n", " "), re.I)
    if not m:
        return None
    body = re.sub(r"\)\s*$", "", m.group(1)).replace(" entities", "")
    return [p.strip(" ()") for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", body) if p.strip(" ()")]


def note_applies(targets: list[str] | None, names: list[str]) -> bool:
    if targets is None:
        return True
    for t in targets:
        T = set(norm_words(t))
        for n in names:
            E = set(norm_words(n))
            if not T or not E:
                continue
            if "".join(sorted(T)) == "".join(sorted(E)) or "".join(norm_words(t)) == "".join(norm_words(n)) \
                    or T <= E or E <= T or len(T & E) / len(T) >= 0.75:
                return True
    return False


def norm_words(s: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", (s or "").lower()):
        w = w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
        out.append({"crossframe": "cross frame"}.get(w, w))
    return " ".join(out).split()


def parse_entities(wb) -> list[dict]:
    out = []
    index = {}
    for r in wb["Index"].iter_rows(min_row=2, values_only=True):
        if r[1]:
            index[str(r[1]).strip()] = clean(r[3])
    for name in wb.sheetnames:
        if index.get(name) == "Help/Guidance":
            continue
        for k, blk in enumerate(parse_tab(wb[name])):
            for e in blk["entities"]:
                names = [n.strip() for n in (e["industry_name"] or "").split("\n") if n.strip()]
                psets = [{**p, "applies_to_targets": note_targets(p["note"]),
                          "applies": note_applies(note_targets(p["note"]), names + [e["dd_name"] or ""])}
                         for p in blk["psets"]]
                out.append({"tab": name, "category": index.get(name), "block": k, "row": e["row"],
                            "industry_name": e["industry_name"], "industry_names": names,
                            "ifc_name": e["ifc_name"], "ifc": parse_ifc_name(e["ifc_name"]),
                            "dd_name": e["dd_name"], "description": e["description"],
                            "attributes": blk["attributes"], "psets": psets,
                            "n_entities_in_block": len(blk["entities"])})
    return out


def parse_concepts(wb) -> list[dict]:
    ws = wb["US B&S Concepts"]
    out, stack, last = [], {}, None
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        r = list(r) + [None] * 12
        depth = next((j for j in range(8) if clean(r[j])), None)
        mapping, dd, note = clean(r[8]), clean(r[10]), clean(r[11])
        if depth is None:
            if mapping and last is not None:   # an "or" row: another mapping for the concept above
                last["ifc_mappings"].append({"text": mapping, **parse_ifc_name(mapping)})
                last["dd_names"].append(dd)
            continue
        concept = clean(r[depth])
        stack = {d: c for d, c in stack.items() if d < depth}
        stack[depth] = concept
        row = {"row": i, "depth": depth, "concept": concept,
               "path": [stack[d] for d in sorted(stack)],
               "see_below": bool(re.search(r"\(see below\)", concept or "", re.I)),
               "ifc_mappings": ([{"text": mapping, **parse_ifc_name(mapping)}] if mapping else []),
               "dd_names": [dd] if mapping else [], "note": note}
        out.append(row)
        last = row
    return out


# --------------------------------------------------------------------------- bSDD cross-check
_DT = {  # bSDD's coarse dataType for each IFC measure / defined type family
    "String": {"IFCLABEL", "IFCTEXT", "IFCIDENTIFIER", "IFCURIREFERENCE", "IFCDATE", "IFCDATETIME",
               "IFCDURATION", "IFCTIME"},
    "Boolean": {"IFCBOOLEAN", "IFCLOGICAL"},
    "Integer": {"IFCINTEGER", "IFCCOUNTMEASURE", "IFCPOSITIVEINTEGER"},
}


def bsdd_kind(ifc_type: str | None) -> str | None:
    if not ifc_type:
        return None
    t = ifc_type.upper()
    if t.startswith("PENUM_") or t.startswith("PEENUM"):
        return "String"
    for k, v in _DT.items():
        if t in v:
            return k
    return "Real"


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def cross_check(entities: list[dict]) -> dict:
    from eval.usbridge import bsdd
    bsdd.OFFLINE = True
    d = bsdd.load()
    classes = d["classes"]
    by_code = {c["code"]: c for c in classes.values()}
    by_dd = {norm(c["code"].removeprefix("usBridge_")): c for c in classes.values()}
    props = {p["code"]: p for p in d["properties"].values()}
    diffs = defaultdict(list)
    seen_classes = set()
    for e in entities:
        dd = e.get("dd_name")
        if not dd:
            continue
        c = by_dd.get(norm(dd))
        if c is None:
            diffs["workbook_dd_name_not_in_bsdd"].append({"tab": e["tab"], "dd_name": dd, "industry_name": e["industry_name"]})
            continue
        seen_classes.add(c["code"])
        if norm(c.get("name")) != norm(e["industry_names"][0] if e["industry_names"] else ""):
            diffs["name_differs"].append({"dd_name": dd, "workbook": e["industry_name"], "bsdd": c.get("name")})
        rel = [x.get("relatedClassUri", "").rsplit("/", 1)[-1].upper() for x in c.get("classRelations") or []]
        ents = [x.upper() for x in c.get("relatedIfcEntityNames") or []]
        ifc = e["ifc"].get("entity")
        if ifc and ifc not in rel and ifc not in ents:
            diffs["ifc_class_differs"].append({"dd_name": dd, "workbook": e["ifc_name"], "bsdd_relations": rel,
                                              "bsdd_relatedIfcEntityNames": ents})
        wb_props = {(p["pset"], q["name"]): q for p in e["psets"] if p["source"] == "usbridge" and p["applies"]
                    for q in p["properties"]}
        bs_props = {(cp.get("propertySet"), cp.get("propertyCode")): cp for cp in c.get("classProperties") or []
                    if str(cp.get("propertySet") or "").startswith("usBrPset")}
        for k in sorted(set(wb_props) - set(bs_props), key=str):
            note = next((p["note"] for p in e["psets"] if p["pset"] == k[0]), None)
            diffs["property_in_workbook_not_on_bsdd_class"].append({"dd_name": dd, "pset": k[0], "property": k[1],
                                                                    "pset_note": note})
        for k in sorted(set(bs_props) - set(wb_props), key=str):
            diffs["property_on_bsdd_class_not_in_workbook"].append({"dd_name": dd, "pset": k[0], "property": k[1]})
        for k in sorted(set(wb_props) & set(bs_props), key=str):
            w, b = wb_props[k], bs_props[k]
            want = bsdd_kind(w.get("data_type"))
            if want and b.get("dataType") and want != b["dataType"]:
                diffs["datatype_differs"].append({"dd_name": dd, "pset": k[0], "property": k[1],
                                                  "workbook": w.get("data_type"), "bsdd": b.get("dataType")})
            wenum = set(w.get("enumeration") or [])
            p = props.get(k[1])
            benum = {v.get("value") for v in (p or {}).get("allowedValues") or []}
            if (wenum or benum) and wenum != benum:
                diffs["enumeration_differs"].append({"dd_name": dd, "pset": k[0], "property": k[1],
                                                     "only_workbook": sorted(wenum - benum),
                                                     "only_bsdd": sorted(benum - wenum)})
    for code in sorted(set(by_code) - seen_classes):
        kind = by_code[code].get("classType")
        key = "bsdd_class_not_in_workbook" if kind == "Class" else f"bsdd_{(kind or 'other').lower()}_records"
        diffs[key].append({"code": code, "name": by_code[code].get("name"), "classType": kind})
    # property-level, independent of classes: the workbook's unique property list vs bSDD properties
    summary = {k: len(v) for k, v in diffs.items()}
    summary["bsdd_classes"] = len(classes)
    summary["bsdd_properties"] = len(props)
    # dedupe the class-level property differences into (pset, property) pairs
    for k in ("property_in_workbook_not_on_bsdd_class", "property_on_bsdd_class_not_in_workbook",
              "datatype_differs", "enumeration_differs"):
        summary[k + "_distinct_pset_property"] = len({(x["pset"], x["property"]) for x in diffs[k]})
    return {"summary": summary, **diffs}


def main():
    OUT.mkdir(exist_ok=True)
    wb = openpyxl.load_workbook(WB, data_only=True)
    ents = parse_entities(wb)
    with open(OUT / "workbook_entities.jsonl", "w", encoding="utf-8") as fh:
        for e in ents:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    concepts = parse_concepts(wb)
    with open(OUT / "concepts.jsonl", "w", encoding="utf-8") as fh:
        for c in concepts:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    import sys
    if "--no-bsdd" in sys.argv:
        cc = {"summary": "skipped (--no-bsdd)"}
    else:
        cc = cross_check(ents)
        (OUT / "workbook_vs_bsdd.json").write_text(json.dumps(cc, indent=1, ensure_ascii=False), encoding="utf-8")
        SUMMARY.mkdir(exist_ok=True)               # the counts only; the rows quote the workbook
        (SUMMARY / "workbook_vs_bsdd.json").write_text(json.dumps(cc["summary"], indent=1), encoding="utf-8")
    print(json.dumps({
        "entity_tabs": len({e["tab"] for e in ents}), "entity_rows": len(ents),
        "with_dd_name": sum(1 for e in ents if e["dd_name"]),
        "usbridge_psets": len({p["pset"] for e in ents for p in e["psets"] if p["source"] == "usbridge"}),
        "ifc_psets": len({p["pset"] for e in ents for p in e["psets"] if p["source"] == "ifc"}),
        "concepts": len(concepts), "concepts_mapped": sum(1 for c in concepts if c["ifc_mappings"]),
        "by_category": dict(Counter(e["category"] for e in ents)),
        "bsdd": cc["summary"]}, indent=1))


if __name__ == "__main__":
    main()
