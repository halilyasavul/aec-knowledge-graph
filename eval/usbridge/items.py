"""Step 5 — test items: the generator's only input.

    python -X utf8 -m eval.usbridge.items

Writes eval/usbridge/items.jsonl:
  one item per aligned IDM-1 entity   id = usb-<idm id>; request_text = the entity's subsection
                                      heading and prose, the IDM's cardinality sentence, and the
                                      entity's table rows (Entity / Property Set / Property) — IDM-1
                                      wording only, nothing added
  one whole-document item             id = usb-section4; the whole Section 4 (front matter, every
                                      subsection's prose and tables, unaligned entities included)
Every item also carries reference_spec_ids (answer key; the runner must pass request_text only).
The whole-document item's reference is every specification of the four IDS files (the
PropertySets specs enter through expansion); reference_spec_ids_aligned lists those reached by the
alignment.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def table_text(e: dict) -> str:
    lines = [f"Entity: {e['entity']}"]
    for g in e["property_groups"]:
        lines.append(f"  Property Set: {g['name']}" if g["name"] else "  Property Set: (none)")
        lines += [f"    - {p}" for p in g["properties"]]
    return "\n".join(lines)


def section_head(sec: dict) -> str:
    return "\n\n".join([f"{sec['section']}--{sec['title']}"] + sec["prose"])


def main():
    ents = load(ROOT / "idm" / "entities.jsonl")
    s4 = json.loads((ROOT / "idm" / "section4.json").read_text(encoding="utf-8"))
    secs = {s["section"]: s for s in s4["sections"]}
    rule = s4["cardinality_rule"]
    specs = [s for s in load(ROOT / "reference" / "specs_expanded.jsonl")]
    by_idm = defaultdict(list)
    match = defaultdict(set)
    with open(ROOT / "alignment.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            match[r["idm_id"]].add(r["idm_wb_match"])
            for sid in (r["ids_spec_ids"] or "").split():
                if sid not in by_idm[r["idm_id"]]:
                    by_idm[r["idm_id"]].append(sid)

    items = []
    for e in ents:
        if not by_idm.get(e["id"]):
            continue
        text = "\n\n".join([section_head(secs[e["section"]]), rule, table_text(e)])
        items.append({"id": f"usb-{e['id']}", "setting": "entity", "idm_id": e["id"], "idm_entity": e["entity"],
                      "idm_section": e["section"], "idm_pages": e["pages"],
                      "request_text": text, "n_idm_properties": e["n_properties"],
                      "alignment": sorted(match[e["id"]]),
                      "reference_spec_ids": by_idm[e["id"]]})
    parts = [p["text"] for p in s4["front_matter"]]
    for sec in s4["sections"]:
        parts.append(section_head(sec))
        parts += [table_text(e) for e in ents if e["section"] == sec["section"]]
    aligned = sorted({sid for v in by_idm.values() for sid in v})
    items.append({"id": "usb-section4", "setting": "document", "request_text": "\n\n".join(parts),
                  "n_idm_entities": len(ents), "n_idm_properties": sum(e["n_properties"] for e in ents),
                  "reference_spec_ids": [s["spec_id"] for s in specs],
                  "reference_spec_ids_aligned": aligned})
    with open(ROOT / "items.jsonl", "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    ent_items = [i for i in items if i["setting"] == "entity"]
    print(json.dumps({
        "entity_items": len(ent_items), "document_items": 1,
        "request_chars_entity_median": sorted(len(i["request_text"]) for i in ent_items)[len(ent_items) // 2],
        "request_chars_document": len(items[-1]["request_text"]),
        "reference_specs_per_entity_item": {"min": min(len(i["reference_spec_ids"]) for i in ent_items),
                                            "median": sorted(len(i["reference_spec_ids"]) for i in ent_items)[len(ent_items) // 2],
                                            "max": max(len(i["reference_spec_ids"]) for i in ent_items)},
        "document_reference_specs": len(items[-1]["reference_spec_ids"]),
        "document_reference_specs_aligned": len(aligned)}, indent=1))


if __name__ == "__main__":
    main()
