"""Draft the determinacy annotations for review (work order v5 §4).

    python -m eval.determinacy            # writes eval/annotations/determinacy.draft.jsonl + review.md

A target facet is *undetermined* when the request text does not carry the information
needed to reproduce it. Two kinds, because they relax the reference differently:

  scope="facet"  the requirement is not mentioned in the request at all -> drop the
                 requirement from the relaxed reference.
  scope="value"  the requirement is described, but its exact value / allowed-value list /
                 pattern is not stated -> keep the requirement, drop the value constraint.

Mapping a described property to its IFC name (e.g. "fire resistance class" on a wall ->
Pset_WallCommon.FireRating) is the schema knowledge under test, so a property-set or
property name is never marked undetermined.

This script only drafts. A human reviews the draft and saves it as
eval/annotations/determinacy.jsonl; nothing is scored against an unreviewed draft.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from eval.common import EVAL_DIR, RUNS_DIR, TESTSET_DIR, graph_psets, ifc_only, load_tasks

ANN_DIR = EVAL_DIR / "annotations"
DRAFT = ANN_DIR / "determinacy.draft.jsonl"
REVIEWED = ANN_DIR / "determinacy.jsonl"
REVIEW_MD = ANN_DIR / "determinacy_review.md"

BOUND_WORDS = re.compile(
    r"\b(positive|greater|more than|at least|minimum|min\.|mindestens|maximum|max\.|maximal|"
    r"höchstens|hoechstens|nicht mehr als|no more than|at most|zwischen|between|kleiner|larger)\b",
    re.IGNORECASE)
ENUM_HIT_RATIO = 0.5          # at least half the allowed values must appear in the text


def fold(s: str) -> str:
    """Casefold and strip accents so 'Straße' matches 'strasse'-ish text."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).casefold()


def mentions(text: str, token: str) -> bool:
    t = fold(token).strip()
    if not t:
        return False
    return re.search(rf"(?<![0-9a-z]){re.escape(t)}(?![0-9a-z])", fold(text)) is not None


def described_indices(source: str, spec_no: str) -> set[int]:
    """1-based facet indices that carry a description, from facet_tasks.jsonl."""
    out = set()
    for row in load_tasks(TESTSET_DIR / "facet_tasks.jsonl"):
        if row["source"] == source:
            sid, _, fid = row["id"].rpartition(".")
            if sid.endswith("#" + spec_no):
                out.add(int(fid))
    return out


def facet_label(f: dict) -> str:
    k = f["facet"]
    if k == "property":
        return f"property {f.get('propertySet')}.{f.get('baseName')}"
    if k == "attribute":
        return f"attribute {f.get('name')}"
    if k == "entity":
        return f"entity {f.get('name')} {f.get('predefinedType') or ''}".strip()
    return f"{k} {f.get('value') or ''}".strip()


def restriction_parts(v: str | None) -> dict:
    if not v or not v.startswith("RESTRICTION("):
        return {"simple": v} if v else {}
    body = v[len("RESTRICTION("):-1]
    out: dict = {}
    for m in re.split(r",(?=\w+=)", body):
        if "=" not in m:
            continue
        k, x = m.split("=", 1)
        out.setdefault(k, []).append(x)
    return out


def judge(f: dict, prompt_text: str, is_described: bool) -> dict | None:
    """Return an annotation dict when the facet is undetermined, else None."""
    if not is_described:
        return {"determined": False, "scope": "facet",
                "reason": "requirement has no description in the source IDS, so the request never mentions it"}
    parts = restriction_parts(f.get("value"))
    if not parts:
        return None
    if "enumeration" in parts:
        vals = parts["enumeration"]
        hit = [v for v in vals if mentions(prompt_text, v)]
        if len(hit) / len(vals) < ENUM_HIT_RATIO:
            return {"determined": False, "scope": "value",
                    "reason": f"allowed-value list not stated: {len(hit)}/{len(vals)} values appear in the "
                              f"request ({', '.join(hit[:4]) or 'none'})"}
        return None
    if "simple" in parts:
        if not mentions(prompt_text, parts["simple"]):
            return {"determined": False, "scope": "value",
                    "reason": f"exact value {parts['simple']!r} is not stated in the request"}
        return None
    if "pattern" in parts:
        pat = parts["pattern"][0]
        literals = [t for t in re.findall(r"[A-Za-z0-9 ]{3,}", pat) if t.strip()]
        if not literals or not any(mentions(prompt_text, t) for t in literals):
            return {"determined": False, "scope": "value",
                    "reason": f"pattern {pat!r} is not derivable from the request text"}
        return None
    bounds = {k: v for k, v in parts.items() if k.startswith(("min", "max")) or k.endswith("Length")}
    if bounds:
        nums = [x for vs in bounds.values() for x in vs]
        if any(mentions(prompt_text, n) for n in nums) or BOUND_WORDS.search(prompt_text):
            return None
        return {"determined": False, "scope": "value",
                "reason": f"bound {bounds} not stated in the request (no number and no comparative wording)"}
    return None


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="draft for all 185 items (default: the IFC-only items under study)")
    ap.add_argument("--graph-cache", default=str(RUNS_DIR / "spec_gemini-2.5-flash"),
                    help="run dir holding graph_psets.json, used to select IFC-only items")
    args = ap.parse_args(argv)
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    rows, md = [], ["# Determinacy draft — please review",
                    "",
                    "One line per target facet that the draft marks **undetermined**.",
                    "`scope=facet` drops the requirement; `scope=value` keeps the requirement but drops its value constraint.",
                    "Edit/delete lines in `determinacy.draft.jsonl`, then save it as `determinacy.jsonl`.",
                    ""]
    tasks = load_tasks(TESTSET_DIR / "spec_tasks.jsonl")
    if not args.all:
        psets = graph_psets(Path(args.graph_cache))
        if psets is None:
            raise SystemExit("graph needed to select IFC-only items (or pass --all)")
        tasks = [t for t in tasks if ifc_only(t, psets)]
    print(f"drafting over {len(tasks)} items")
    cache: dict = {}
    for t in tasks:
        src, _, spec_no = t["id"].partition("#")
        key = (src, spec_no)
        if key not in cache:
            cache[key] = described_indices(src, spec_no)
        described = cache[key]
        prompt_text = " \n".join(t["prompt"]["requirements"])
        flagged = []
        for i, f in enumerate(t["target"]):
            ann = judge(f, prompt_text, (i + 1) in described)
            if ann is None:
                continue
            rows.append({"id": t["id"], "facet_index": i, **ann, "facet": facet_label(f),
                         "value": f.get("value")})
            flagged.append((i, ann, f))
        if flagged:
            md.append(f"## {t['id']}  ({len(t['target'])} requirements)")
            md.append(f"request: {prompt_text[:300].replace(chr(10), ' / ')}...")
            md.append("")
            for i, ann, f in flagged:
                md.append(f"- facet {i} — {facet_label(f)} — **{ann['scope']}** — {ann['reason']}")
            md.append("")
    with open(DRAFT, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    REVIEW_MD.write_text("\n".join(md), encoding="utf-8")
    n_items = len({r["id"] for r in rows})
    by_scope: dict = {}
    for r in rows:
        by_scope[r["scope"]] = by_scope.get(r["scope"], 0) + 1
    print(f"{len(rows)} undetermined facets across {n_items} items {by_scope}")
    print(f"-> {DRAFT}\n-> {REVIEW_MD}")
    print(f"review, then save as {REVIEWED} — scoring refuses to use the draft")


if __name__ == "__main__":
    main()
