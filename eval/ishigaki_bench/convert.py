"""Ishigaki-IDS-Bench (data/test.jsonl) -> items in the shape of eval/nl_to_ids_testset/spec_tasks.jsonl.

    python -m eval.ishigaki_bench.convert

Reads the English rows only. The request is the last user message after its two header lines
("IDS Version: ...", "filename: ...") — the filename carries the row id, the version is replaced
by the harness's own "Target schema" line — kept verbatim as ONE requirement string: the inputs
are already structured, and build_message numbers the list. `applies_to` is the gold's first
applicability entity, as extract_testset.py does for the dev set: the entity is given.

The gold is read mechanically (lxml) and flattened with the same facet_target() as the dev set,
so canon() matches. Every gold file is also validated against data/ids.xsd.

Writes
  eval/ishigaki_bench/spec_tasks_en.jsonl          one item per English row
  eval/ishigaki_bench/item_lists/native_<n>.json   the harness-native ids: single turn, one
                                                   specification, applicability = entity only
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from lxml import etree

from aec_kg.ids.validator import validate_ids_xml
from eval.nl_to_ids_testset.extract_testset import Q, applicability, facet_target, names_in

HERE = Path(__file__).resolve().parent
SRC = HERE / "data" / "test.jsonl"
OUT = HERE / "spec_tasks_en.jsonl"
LISTS = HERE / "item_lists"


def request_text(messages: list[dict]) -> str:
    """The evaluation input is messages[:-1]; for a single turn that is one user message."""
    user = [m for m in messages[:-1] if m["role"] == "user"][-1]["content"]
    lines = user.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("IDS Version:") or lines[i].startswith("filename:")):
        i += 1
    return "\n".join(lines[i:]).strip()


def children(node) -> list:
    return [c for c in node if isinstance(c.tag, str)] if node is not None else []


def convert(row: dict) -> dict:
    gold = row["messages"][-1]["content"]
    root = etree.fromstring(gold.encode("utf-8"))
    title = (root.findtext(f"{Q('info')}/{Q('title')}") or "").strip()
    specs = []
    for sp in root.iter(Q("specification")):
        app = sp.find(Q("applicability"))
        specs.append({"spec_name": sp.get("name"), "ifcVersion": sp.get("ifcVersion"),
                      "applicability": applicability(sp),
                      "applicability_facets": [facet_target(c) for c in children(app)],
                      "minOccurs": app.get("minOccurs") if app is not None else None,
                      "maxOccurs": app.get("maxOccurs") if app is not None else None,
                      "target": [facet_target(c) for c in children(sp.find(Q("requirements")))]})
    first = specs[0]
    kinds = sorted({f["facet"] for s in specs for f in s["applicability_facets"]})
    req = request_text(row["messages"])
    n_turns = sum(1 for m in row["messages"] if m["role"] == "user")
    native = row["turn_type"] == "single_turn" and len(specs) == 1 and kinds == ["entity"]
    # several specifications: every distinct entity is given, in gold order; the requirements of
    # all specifications form the target for facet F1, as parse_candidate concatenates them
    applies_to = first["applicability"]
    entities = list(dict.fromkeys(s["applicability"].get("entity") for s in specs if s["applicability"].get("entity")))
    if len(entities) > 1:
        applies_to = {"entity": ", ".join(entities)}
    target = [f for s in specs for f in s["target"]]
    return {"id": row["id"], "source": "ishigaki", "ids_title": title, "spec_name": first["spec_name"],
            "applicability": first["applicability"], "n_requirements": len(target),
            "any_leak": any(n in req for s in specs for t in s["target"] for n in names_in(t)),
            "prompt": {"applies_to": applies_to, "requirements": [req]},
            "target": target,
            "ifc_versions": row["ifc_versions"], "input_format": row["input_format"],
            "turn_type": row["turn_type"], "n_user_turns": n_turns, "domain": row["domain"],
            "n_specs": len(specs), "applicability_kinds": kinds, "harness_native": native,
            "specs": specs, "gold_ids": gold}


def main():
    rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    en = [r for r in rows if r["language"] == "en"]
    items, xsd_bad = [], []
    for r in en:
        it = convert(r)
        ok, errs = validate_ids_xml(it["gold_ids"], strict=True)
        it["gold_xsd_valid"] = ok
        if not ok:
            xsd_bad.append((r["id"], errs[:2]))
        items.append(it)
    with open(OUT, "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    native = [it["id"] for it in items if it["harness_native"]]
    LISTS.mkdir(exist_ok=True)
    (LISTS / f"native_{len(native)}.json").write_text(json.dumps(native, indent=0))
    # stage 2: single turn, several specifications and/or attribute/property applicability
    stage2 = [it["id"] for it in items if not it["harness_native"] and it["turn_type"] == "single_turn"]
    (LISTS / f"stage2_single_turn_{len(stage2)}.json").write_text(json.dumps(stage2, indent=0))
    print(f"stage 2 (single turn, not native): {len(stage2)} -> item_lists/stage2_single_turn_{len(stage2)}.json")
    print(f"{len(en)} English rows -> {OUT.relative_to(HERE.parent.parent)}")
    print(f"harness-native: {len(native)} -> item_lists/native_{len(native)}.json; by input format "
          f"{dict(collections.Counter(it['input_format'] for it in items if it['harness_native']))}")
    why = collections.Counter()
    for it in items:
        if it["harness_native"]:
            continue
        why[(it["turn_type"], "multi-spec" if it["n_specs"] > 1 else "one spec",
             "entity-only app" if it["applicability_kinds"] == ["entity"] else "+".join(it["applicability_kinds"]))] += 1
    print("not native:", dict(why))
    print(f"gold XSD-invalid: {len(xsd_bad)}", xsd_bad[:5])


if __name__ == "__main__":
    main()
