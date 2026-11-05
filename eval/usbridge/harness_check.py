"""Step 8 — harness check: the scorer on reference vs reference (must be 100%), and the gaps.

    python -X utf8 -m eval.usbridge.harness_check

Two identity runs, written under eval/runs/ (never committed):
  usbridge-refref-expanded    task targets from specs_expanded.jsonl; candidate = the reference
                              the scorer itself builds (score.build_reference) -> tests scoring
  usbridge-refref-official    task targets from specs.jsonl (unexpanded); candidate = the official
                              <specification> elements copied verbatim from the HDR files -> tests
                              that the flattening loses nothing the scorer can see
Each runs `python -m eval.score <run> <tasks> eval/models` unchanged (metric code is not
touched). The report reads scores.csv: facet F1, XSD validity, S1 on the witness model, outcome
equivalence on the sample models, and every `wit_unsupported` / `wit_problems` note.
Writes eval/usbridge/summary/harness_check.json.
"""
from __future__ import annotations

import copy
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from lxml import etree

from eval import score
from eval.common import safe_name

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "summary"          # committed: counts and totals only
RUNS = ROOT.parent / "runs"
NS = "http://standards.buildingsmart.org/IDS"


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


KEEP = {"facet", "name", "predefinedType", "propertySet", "baseName", "value", "system", "entity",
        "entityPredefinedType", "dataType", "cardinality", "uri", "relation"}


def clean(f: dict) -> dict:
    return {k: v for k, v in f.items() if k in KEEP}


def task(item: dict, specs: dict) -> dict:
    sps = [specs[s] for s in item["reference_spec_ids"] if s in specs]
    first = next((s["applies_to"] for s in sps if s["applies_to"]), {}) or {}
    return {"id": item["id"], "source": "usbridge", "spec_name": item["id"],
            "applicability": {"entity": first.get("entity"), **({"predefinedType": first["predefinedType"]}
                                                                 if first.get("predefinedType") else {})},
            "target": [clean(f) for s in sps for f in s["requirements"]],
            "specs": [{"spec_name": s["name"], "applicability_facets": [clean(f) for f in s["applicability"]["facets"]],
                       "target": [clean(f) for f in s["requirements"]]} for s in sps],
            "reference_spec_ids": [s["spec_id"] for s in sps]}


def official_ids(spec_ids: list[str]) -> bytes:
    """The HDR <specification> elements, copied as they are, in one IDS document."""
    trees = {}
    root = etree.Element(f"{{{NS}}}ids", nsmap={"ids": NS, "xs": "http://www.w3.org/2001/XMLSchema",
                                                "xsi": "http://www.w3.org/2001/XMLSchema-instance"})
    root.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation",
             f"{NS} http://standards.buildingsmart.org/IDS/1.0/ids.xsd")
    info = etree.SubElement(root, f"{{{NS}}}info")
    etree.SubElement(info, f"{{{NS}}}title").text = "official usBridge specifications"
    out = etree.SubElement(root, f"{{{NS}}}specifications")
    for sid in spec_ids:
        stem, k = sid.rsplit("#", 1)
        if stem not in trees:
            trees[stem] = etree.parse(str(ROOT / "source" / f"{stem}.ids")).findall(f".//{{{NS}}}specification")
        out.append(copy.deepcopy(trees[stem][int(k)]))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def run(variant: str, items: list[dict], specs: dict) -> dict:
    run_dir = RUNS / f"usbridge-refref-{variant}"
    gen = run_dir / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    tasks = [task(it, specs) for it in items]
    tasks_path = run_dir / "tasks.jsonl"
    with open(tasks_path, "w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(t) + "\n")
    for t in tasks:
        body = score.build_reference(t) if variant == "expanded" else official_ids(t["reference_spec_ids"])
        (gen / f"{safe_name(t['id'])}.ids").write_bytes(body)
    score.main([str(run_dir), str(tasks_path), str(ROOT.parent / "models")])
    rows = list(csv.DictReader(open(run_dir / "scores.csv", encoding="utf-8")))
    num = lambda r, k: float(r[k]) if r.get(k) not in (None, "") else None
    res = {"items": len(rows),
           "facet_f1_1": sum(1 for r in rows if num(r, "facet_f1") == 1.0),
           "xsd_valid": sum(1 for r in rows if r.get("xsd_valid") == "1"),
           "ref_xsd_valid": sum(1 for r in rows if r.get("ref_xsd_valid") == "1"),
           "wit_s1_1": sum(1 for r in rows if num(r, "wit_outcome_equiv") == 1.0),
           "wit_scored": sum(1 for r in rows if num(r, "wit_outcome_equiv") is not None),
           "wit_unverified": sum(1 for r in rows if r.get("wit_direction") == "witness_unverified"),
           "vf0_equiv_1": sum(1 for r in rows if num(r, "vf0_outcome_equiv") == 1.0),
           "vf0_scored": sum(1 for r in rows if num(r, "vf0_outcome_equiv") is not None),
           "vf1_equiv_1": sum(1 for r in rows if num(r, "vf1_outcome_equiv") == 1.0),
           "vf1_scored": sum(1 for r in rows if num(r, "vf1_outcome_equiv") is not None),
           "not_perfect": [{k: r.get(k) for k in ("id", "facet_f1", "xsd_valid", "xsd_error", "wit_outcome_equiv",
                                                   "wit_direction", "wit_diverging", "vf0_outcome_equiv",
                                                   "vf1_outcome_equiv", "wit_exec_error", "vf0_exec_error")}
                           for r in rows if num(r, "facet_f1") != 1.0 or num(r, "wit_outcome_equiv") not in (1.0, None)
                           or num(r, "vf0_outcome_equiv") not in (1.0, None)],
           "unsupported": Counter(), "problems": Counter()}
    for r in rows:
        for u in filter(None, (r.get("wit_unsupported") or "").split(" | ")):
            res["unsupported"][u[:110]] += 1
        for p in filter(None, (r.get("wit_problems") or "").split(" | ")):
            res["problems"][p.split(":")[0][:60]] += 1
    res["unsupported"] = dict(res["unsupported"].most_common(40))
    res["problems"] = dict(res["problems"].most_common(40))
    return res


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    items = load(ROOT / "items.jsonl")
    if "--entity-only" in argv:
        items = [i for i in items if i["setting"] == "entity"]
    out = {}
    for variant, src in (("expanded", "specs_expanded.jsonl"), ("official", "specs.jsonl")):
        if argv and variant not in argv and not any(a.startswith("--") for a in argv):
            continue
        specs = {s["spec_id"]: s for s in load(ROOT / "reference" / src)}
        out[variant] = run(variant, items, specs)
    SUMMARY.mkdir(exist_ok=True)
    prev = SUMMARY / "harness_check.json"
    merged = json.loads(prev.read_text(encoding="utf-8")) if prev.exists() else {}
    merged.update(out)
    prev.write_text(json.dumps(merged, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("not_perfect",)} for k, v in out.items()},
                     indent=1))


if __name__ == "__main__":
    main()
