"""Step 3 — the generator input: AASHTO IDM 1st Edition (2023), Section 4 "Exchange Requirement".

    python -X utf8 -m eval.usbridge.idm

Writes
  eval/usbridge/idm/entities.jsonl  one row per IDM-1 entity (the "Entity" column of a Section 4
      table): the entity name as the IDM writes it ("(Continued)" removed), its subsection
      (4.1.x, title), the subsection's prose paragraphs, and its property groups ("Property Set"
      column) with their properties ("Property" column), in table order. IDM wording only; no IFC
      names are added.
  eval/usbridge/idm/section4.json   the Section 4 front matter (4 intro, 4.1 intro, the
      cardinality rule, figure caption) and the subsection prose, for the whole-document item;
      plus a parse log (watermark lines removed, inferred entity labels, wrapped lines joined).

Text comes from PyMuPDF: tables are located with page.find_tables(), but every cell is re-read
with page.get_text(clip=cell) because the table extractor garbles ligatures ("Efef ctive"). A
property that wraps onto a second line is rejoined when the second line is indented or the first
has an unclosed parenthesis. Watermark lines (licensee stamp, "Not for Resale", backtick runs,
the copyright footer) are dropped everywhere, inside cells too.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent
PDF = ROOT / "source" / "AASHTO_IDM_1st_Edition_2023.pdf"
OUT = ROOT / "idm"
WATERMARK = re.compile(
    r"(Copyright American Association of State Highway|Provided by Accuris|Licensee=|Resale, \d\d/\d\d/\d{4}|"
    r"[A-Z]{2}/\d{8,}|Denver, .*Officials\.|No reproduction or networking|© 2023 by the American Association|"
    r"All rights reserved\. Duplication|is a violation of applicable law|^[-`,]{6,}$|[`]{3,}|"
    r"^Information Delivery Manual \(IDM\) for the Design|^to Construction Data Exchange for Highway Bridges|"
    r"^Section 4: Exchange Requirement$|^4-\d+$|^Continued (on next|from previous) page$)")
HEADING = re.compile(r"^(4\.1(?:\.\d+)?)\s*[—–-]+\s*(.+)$")
HEADER_ROW = ["Entity", "Property Set", "Property"]
LOG = Counter()
NOTES: list[str] = []


def keep(line: str) -> bool:
    if WATERMARK.search(line.strip()):
        LOG["watermark_lines_removed"] += 1
        return False
    return bool(line.strip())


def cell_lines(page, rect) -> list[tuple[float, str]]:
    if rect is None:
        return []
    d = page.get_text("dict", clip=fitz.Rect(rect))
    out = []
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            s = re.sub(r"\s+", " ", "".join(sp["text"] for sp in ln["spans"])).strip()
            if s and keep(s):
                out.append((ln["bbox"][0], ln["bbox"][1], s))
    out.sort(key=lambda x: (round(x[1]), x[0]))
    return [(x, s) for x, _, s in out]


def dehyphen(s: str) -> str:
    """'Informa- tion' (a line break inside a word) -> 'Information'."""
    return re.sub(r"([a-z])- ([a-z])", r"\1\2", s)


def join_name(lines) -> str:
    return dehyphen(re.sub(r"\s+", " ", " ".join(s for _, s in lines)).strip())


def split_items(lines) -> list[str]:
    """One property per line; a wrapped line (indented, or after an unclosed '(') is joined."""
    if not lines:
        return []
    base = min(x for x, _ in lines)
    items: list[str] = []
    for x, s in lines:
        if items and (x > base + 2 or items[-1].count("(") > items[-1].count(")")):
            items[-1] = f"{items[-1]} {s}"
            LOG["wrapped_lines_joined"] += 1
        else:
            items.append(s)
    return [dehyphen(s) for s in items]


def page_label(page) -> str | None:
    for ln in page.get_text().split("\n"):
        if re.fullmatch(r"\s*4-\d+\s*", ln):
            return ln.strip()
    return None


def prose_blocks(page, tables) -> list[tuple[float, str]]:
    """Text blocks outside the tables, watermark-free, dehyphenated; (y, text)."""
    out = []
    for b in page.get_text("blocks", flags=fitz.TEXT_DEHYPHENATE):
        y0, y1 = b[1], b[3]
        if any(t.bbox[1] - 2 <= y0 <= t.bbox[3] + 2 for t in tables):
            continue
        lines = [ln.strip() for ln in b[4].split("\n") if keep(ln)]
        if lines:
            out.append((y0, dehyphen(re.sub(r"\s+", " ", " ".join(lines)).strip())))
    return out


def main():
    OUT.mkdir(exist_ok=True)
    doc = fitz.open(str(PDF))
    start = next(i for i in range(doc.page_count)
                 if re.search(r"^4\.1\s*[—–]\s*EXCHANGE REQUIREMENT", doc[i].get_text(), re.M))
    events = []        # ("heading", no, title) | ("prose", text) | ("table", rows, page_label)
    for pno in range(start, doc.page_count):
        page = doc[pno]
        if re.search(r"^\s*Section 5:", page.get_text(), re.M | re.I):
            break
        tables = page.find_tables().tables
        items = [(y, "prose", s) for y, s in prose_blocks(page, tables)]
        for t in tables:
            rows = []
            for r in t.rows:
                cells = [cell_lines(page, c) for c in r.cells]
                if [join_name(c) for c in cells] == HEADER_ROW:
                    continue
                rows.append(cells)
            items.append((t.bbox[1], "table", rows))
        for y, kind, payload in sorted(items, key=lambda x: x[0]):
            if kind == "table":
                events.append(("table", payload, page_label(page), pno + 1))
                continue
            m = HEADING.match(payload)
            if m:
                events.append(("heading", m.group(1), m.group(2).strip()))
            elif payload.startswith("Figure 4.1-1"):
                events.append(("figure", payload))
            elif payload.lower() != "section 4: exchange requirement":
                events.append(("prose", payload))

    # -------------------------------------------------------------- walk the events
    front, sections, entities = [], {}, []
    sec, cur_ent, cur_group = None, None, None
    tables = [e for e in events if e[0] == "table"]
    t_index = 0
    for ev in events:
        if ev[0] == "heading":
            if ev[1] == "4.1":
                front.append({"kind": "heading", "text": f"{ev[1]}--{ev[2]}"})
                continue
            sec = {"section": ev[1], "title": ev[2], "prose": []}
            sections[ev[1]] = sec
            cur_ent = cur_group = None
            continue
        if ev[0] in ("prose", "figure"):
            if sec is None:
                front.append({"kind": ev[0], "text": ev[1]})
            elif not any(e["section"] == sec["section"] for e in entities):
                sec["prose"].append(ev[1])     # prose before the subsection's first table
            else:
                sec.setdefault("prose_after_tables", []).append(ev[1])
            continue
        rows, label, pdf_page = ev[1], ev[2], ev[3]
        t_index += 1
        for k, (ent_l, grp_l, prop_l) in enumerate(rows):
            name = join_name(ent_l)
            if name:
                base = re.sub(r"\s*\((Continued|Cont\w*)\)\s*$", "", name).strip()
                if not (cur_ent and base == cur_ent["entity"]):
                    cur_ent = {"entity": base, "section": sec["section"], "section_title": sec["title"],
                               "pages": [], "pdf_pages": [], "property_groups": []}
                    entities.append(cur_ent)
                    cur_group = None
            elif cur_ent is None or (k == 0 and _orphan(tables, t_index, cur_ent)):
                inferred = _orphan(tables, t_index, cur_ent)
                NOTES.append(f"page {label}: table starts without an entity label; rows assigned to "
                             f"'{inferred}' because the next table continues it")
                LOG["entity_labels_inferred"] += 1
                cur_ent = {"entity": inferred, "section": sec["section"], "section_title": sec["title"],
                           "pages": [], "pdf_pages": [], "property_groups": [], "label_inferred": True}
                entities.append(cur_ent)
                cur_group = None
            if label not in cur_ent["pages"]:
                cur_ent["pages"].append(label)
                cur_ent["pdf_pages"].append(pdf_page)
            gname = join_name(grp_l) or None
            props = split_items(prop_l)
            if gname is None and cur_group is not None:
                cur_group["properties"] += props           # a group split across a page break
                LOG["groups_continued_across_rows"] += 1
                continue
            cur_group = {"name": gname, "properties": props}
            cur_ent["property_groups"].append(cur_group)

    for i, e in enumerate(entities, 1):
        e["id"] = f"idm1-{i:03d}"
        e["prose"] = sections[e["section"]]["prose"]
        e["n_groups"] = len(e["property_groups"])
        e["n_properties"] = sum(len(g["properties"]) for g in e["property_groups"])
    rule = next((p["text"] for p in front if p["text"].startswith("All listed properties")), None)
    with open(OUT / "entities.jsonl", "w", encoding="utf-8") as fh:
        for e in entities:
            fh.write(json.dumps({k: e[k] for k in ("id", "entity", "section", "section_title", "pages",
                                                   "pdf_pages", "prose", "property_groups", "n_groups",
                                                   "n_properties")} |
                                ({"label_inferred": True} if e.get("label_inferred") else {}),
                                ensure_ascii=False) + "\n")
    (OUT / "section4.json").write_text(json.dumps({
        "front_matter": front, "cardinality_rule": rule,
        "sections": list(sections.values()), "parse_log": dict(LOG), "notes": NOTES},
        indent=1, ensure_ascii=False), encoding="utf-8")
    dup = [k for k, v in Counter(e["entity"] for e in entities).items() if v > 1]
    print(json.dumps({"sections": len(sections), "entities": len(entities),
                      "property_groups": sum(e["n_groups"] for e in entities),
                      "properties": sum(e["n_properties"] for e in entities),
                      "by_section": dict(Counter(f"{e['section']} {e['section_title']}" for e in entities)),
                      "duplicate_entity_names": dup, "cardinality_rule": rule,
                      "log": dict(LOG), "notes": NOTES}, indent=1, ensure_ascii=False))


def _orphan(tables, t_index, cur_ent) -> str | None:
    """The table at t_index (1-based) starts without an entity label. If the following table
    starts with '<X> (Continued)' and X is not the current entity, the rows are X's."""
    if t_index >= len(tables):
        return None
    nxt = tables[t_index][1]
    if not nxt:
        return None
    first = join_name(nxt[0][0])
    m = re.match(r"(.+?)\s*\((Continued|Cont\w*)\)\s*$", first)
    if m and (cur_ent is None or m.group(1).strip() != cur_ent["entity"]):
        return m.group(1).strip()
    return None


if __name__ == "__main__":
    main()
