"""Step 1 — the reference: the four usBridge 2.0 IDS files (IDM 2.0 Appendix 4, HDR, 2026).

    python -X utf8 -m eval.usbridge.reference

Writes
  eval/usbridge/reference/specs.jsonl           one row per specification, all four files
  eval/usbridge/reference/specs_expanded.jsonl  the General / SpatialBreakdown / Classes specs with
                                                every whole-set requirement (propertySet named,
                                                baseName = pattern .*) replaced by the property
                                                list of that set's spec in usBrSpec_PropertySets.ids
  eval/usbridge/summary/counts.json             counts per file

Facets are flattened with the same facet_target() the dev test set and the scorer use
(eval/nl_to_ids_testset/extract_testset.py), so eval.score.canon() reads them unchanged;
`instructions` is added.

Expansion rule. A class spec says "set S is required/optional/prohibited" and S's own spec says
"when S is present, property P is required/optional". Expanded cardinality of P on the class:
  S required + P required -> required;  S required + P optional -> optional;
  S optional + any        -> optional  (P is required only if S is there; IDS cannot say that in one
                                        facet, so the class-level reading is optional)
  S prohibited            -> not expanded; the set-level prohibition stays as it is
A set with no spec in usBrSpec_PropertySets.ids stays set-level (`expanded: false`).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from lxml import etree

from eval.score import extract          # facet_target(): the flattening the scorer reads

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"          # committed: counts and totals only
SRC = ROOT / "source"
OUT = ROOT / "reference"
NS = "http://standards.buildingsmart.org/IDS"
Q = lambda t: f"{{{NS}}}{t}"
FILES = ["usBrSpec_General.ids", "usBrSpec_SpatialBreakdown.ids", "usBrSpec_Classes.ids",
         "usBrSpec_PropertySets.ids"]
ANY = "RESTRICTION(pattern=.*)"


def children(node) -> list:
    return [c for c in node if isinstance(c.tag, str)] if node is not None else []


def facet(el, index: int) -> dict:
    f = extract.facet_target(el)
    if el.get("instructions"):
        f["instructions"] = el.get("instructions")
    f["facet_index"] = index
    return f


def parse_file(name: str) -> list[dict]:
    tree = etree.parse(str(SRC / name))
    info = tree.find(Q("info"))
    title = (info.findtext(Q("title")) or "").strip() if info is not None else ""
    stem = Path(name).stem
    rows = []
    for k, sp in enumerate(tree.findall(".//" + Q("specification"))):
        app = sp.find(Q("applicability"))
        app_f = [facet(c, j) for j, c in enumerate(children(app))]
        ent = next((f for f in app_f if f["facet"] == "entity"), None)
        rows.append({
            "spec_id": f"{stem}#{k}",
            "file": name, "ids_title": title, "index": k,
            "name": sp.get("name"), "description": sp.get("description"),
            "identifier": sp.get("identifier"), "instructions": sp.get("instructions"),
            "ifcVersion": sp.get("ifcVersion"),
            "applicability": {"minOccurs": app.get("minOccurs"), "maxOccurs": app.get("maxOccurs"),
                              "facets": app_f},
            "applies_to": ({"entity": ent.get("name"), **({"predefinedType": ent["predefinedType"]}
                                                          if ent.get("predefinedType") else {})}
                           if ent else None),
            "requirements": [facet(c, j) for j, c in enumerate(children(sp.find(Q("requirements"))))],
        })
    return rows


def _expected(where: str) -> int:
    """'requirements[0..6]' -> 7, 'requirements[8]' -> 1."""
    m = re.search(r"\[(\d+)\.\.(\d+)\]", where)
    return int(m.group(2)) - int(m.group(1)) + 1 if m else 1


def apply_corrections(rows: list[dict], path: Path = OUT / "corrections.json") -> dict:
    """Correct the published defects listed in corrections.json, in place; return counts per id.
    Exits if a correction changes a different number of facets than its occurrences list."""
    import sys
    spec = json.loads(path.read_text(encoding="utf-8"))
    applied = {}
    for c in spec["corrections"]:
        targets = {(o["file"], o["spec"]) for o in c["occurrences"]}
        want = sum(_expected(o["where"]) for o in c["occurrences"])
        n = 0
        for r in rows:
            if (r["file"], r["name"]) not in targets:
                continue
            for f in r["applicability"]["facets"] + r["requirements"]:
                v = f.get(c["field"])
                if not isinstance(v, str):
                    continue
                if v == c["find"]:
                    new = c["replace"]
                elif v.startswith("RESTRICTION(") and re.search(rf"=({re.escape(c['find'])})(?=[,)])", v):
                    new = re.sub(rf"=({re.escape(c['find'])})(?=[,)])", "=" + c["replace"], v)
                else:
                    continue
                f[c["field"]], f.setdefault("published", {})[c["field"]] = new, v
                n += 1
                r.setdefault("corrections", []).append(c["id"])
            if r["applies_to"]:                                    # keep the summary view in step
                ent = next((f for f in r["applicability"]["facets"] if f["facet"] == "entity"), None)
                if ent and ent.get("predefinedType"):
                    r["applies_to"]["predefinedType"] = ent["predefinedType"]
        if n != want:
            sys.exit(f"correction {c['id']}: changed {n} facets, corrections.json lists {want}")
        applied[c["id"]] = n
    return applied


def is_whole_set(f: dict) -> bool:
    return f["facet"] == "property" and f.get("baseName") == ANY and \
        not str(f.get("propertySet") or "").startswith("RESTRICTION(")


def pset_specs(rows: list[dict]) -> dict:
    """propertySet name -> its spec in usBrSpec_PropertySets.ids."""
    out = {}
    for r in rows:
        if r["file"] != "usBrSpec_PropertySets.ids":
            continue
        a = r["applicability"]["facets"]
        if len(a) == 1 and a[0]["facet"] == "property":
            out[a[0]["propertySet"]] = r
    return out


def combine(set_card: str, prop_card: str) -> str:
    return "required" if set_card == "required" and prop_card == "required" else "optional"


def expand(spec: dict, psets: dict) -> dict:
    reqs, notes = [], Counter()
    for f in spec["requirements"]:
        if not is_whole_set(f):
            reqs.append({**f, "origin": "direct"})
            continue
        s, card = f["propertySet"], f.get("cardinality") or "required"
        ps = psets.get(s)
        if card == "prohibited" or ps is None:
            notes["set_prohibited" if card == "prohibited" else "set_without_spec"] += 1
            reqs.append({**f, "origin": "whole_set", "expanded": False,
                         "why_not": "prohibited set" if card == "prohibited" else "no spec in PropertySets.ids"})
            continue
        notes["set_expanded"] += 1
        for p in ps["requirements"]:
            g = {k: v for k, v in p.items() if k != "facet_index"}
            g.update({"cardinality": combine(card, p.get("cardinality") or "required"),
                      "set_cardinality": card, "property_cardinality": p.get("cardinality") or "required",
                      "origin": "expanded", "expanded_from": f["facet_index"],
                      "pset_spec_id": ps["spec_id"]})
            reqs.append(g)
    for i, g in enumerate(reqs):
        g["req_index"] = i
    return {**spec, "requirements": reqs, "expansion": dict(notes)}


def build(corrected: bool) -> tuple[list, list, dict, dict]:
    rows = [r for f in FILES for r in parse_file(f)]
    applied = apply_corrections(rows) if corrected else {}
    psets = pset_specs(rows)
    expanded = [expand(r, psets) for r in rows if r["file"] != "usBrSpec_PropertySets.ids"]
    return rows, expanded, count(rows, expanded, psets), applied


def count(rows: list, expanded: list, psets: dict) -> dict:
    counts = {}
    for name in FILES:
        rs = [r for r in rows if r["file"] == name]
        ex = [r for r in expanded if r["file"] == name]
        kinds = Counter((f["facet"], f.get("cardinality") or "-") for r in rs for f in r["requirements"])
        c = {"specs": len(rs),
             "requirement_facets": sum(len(r["requirements"]) for r in rs),
             "by_kind_cardinality": {f"{k}/{c_}": n for (k, c_), n in sorted(kinds.items())},
             "whole_set_facets": sum(1 for r in rs for f in r["requirements"] if is_whole_set(f)),
             "applicability_kinds": dict(Counter("+".join(sorted({f["facet"] for f in r["applicability"]["facets"]}))
                                                 for r in rs)),
             "applicability_occurs": dict(Counter(f"{r['applicability']['minOccurs']}..{r['applicability']['maxOccurs']}"
                                                  for r in rs))}
        if ex:
            n = Counter()
            for r in ex:
                n.update(r["expansion"])
            c.update({"expanded_requirement_facets": sum(len(r["requirements"]) for r in ex),
                      "expanded_property_facets": sum(1 for r in ex for f in r["requirements"]
                                                      if f.get("origin") == "expanded"),
                      **{f"whole_set_{k}": v for k, v in n.items()}})
        counts[name] = c
    # specs that share one applicability (same entity + predefinedType) in the class-like files
    share = Counter(json.dumps(r["applies_to"], sort_keys=True) for r in rows
                    if r["file"] != "usBrSpec_PropertySets.ids" and r["applies_to"])
    counts["shared_applicability"] = {
        "groups": sum(1 for v in share.values() if v > 1),
        "specs_in_groups": sum(v for v in share.values() if v > 1),
        "largest": sorted(((v, k) for k, v in share.items() if v > 1), reverse=True)[:8],
    }
    counts["pset_specs"] = len(psets)
    unexp = Counter(f["propertySet"] for r in expanded for f in r["requirements"]
                    if f.get("origin") == "whole_set" and f.get("why_not", "").startswith("no spec"))
    counts["sets_without_spec"] = dict(unexp.most_common())
    used = {f["propertySet"] for r in expanded for f in r["requirements"]
            if f["facet"] == "property" and f.get("cardinality") != "prohibited"}
    counts["pset_specs_used_by_no_class"] = sorted(set(psets) - used)
    counts["expanded_facets_total"] = sum(len(r["requirements"]) for r in expanded)
    counts["expanded_property_facets_total"] = sum(1 for r in expanded for f in r["requirements"]
                                                   if f.get("origin") == "expanded")
    return counts


def main():
    OUT.mkdir(exist_ok=True)
    _, _, before, _ = build(corrected=False)
    rows, expanded, after, applied = build(corrected=True)
    with open(OUT / "specs.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "specs_expanded.jsonl", "w", encoding="utf-8") as fh:
        for r in expanded:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    keys = ("expanded_facets_total", "expanded_property_facets_total", "sets_without_spec",
            "pset_specs_used_by_no_class")
    out = {"corrections_applied": applied,
           "before_after": {k: {"published": before[k], "corrected": after[k]} for k in keys},
           "corrected": after}
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "counts.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("corrections_applied", "before_after")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
