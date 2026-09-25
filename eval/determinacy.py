"""Annotate which target facets the request cannot determine (work order v6 §2).

    python -m eval.determinacy      # writes determinacy.draft.jsonl (pass A), determinacy.jsonl
                                    # (pass B, final) and determinacy_review.md (agreement + appendix)

A target facet is *undetermined* when the request text does not carry the information
needed to reproduce it. Two kinds, because they relax the reference differently:

  scope="facet"  the requirement is not mentioned in the request at all -> drop the
                 requirement from the relaxed reference.
  scope="value"  the requirement is described, but its exact value / allowed-value list /
                 pattern is not stated -> keep the requirement, drop the value constraint.

Mapping a described property to its IFC name (e.g. "fire resistance class" on a wall ->
Pset_WallCommon.FireRating) is the schema knowledge under test, so a property-set or
property name is never marked undetermined.

Two passes, as required:
  pass A  the original text heuristics (fraction of values appearing in the request).
  pass B  the final annotation: value lists by a mechanical rule — a list is determined when
          every value is either an IFC allowed value for that property (the schema supplies it)
          or appears in the request; "never mentioned" facets by the model author's own reading,
          recorded case by case in READINGS below.

The annotations are machine-made and were NOT reviewed by a human; that is stated in the report.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from eval.common import (EVAL_DIR, RUNS_DIR, TESTSET_DIR, graph_allowed_values, graph_psets,
                         ifc_only, load_tasks)

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


# =========================================================================== pass B
def enum_values(v: str | None) -> list:
    return re.findall(r"enumeration=([^,)]+)", v or "")


def judge_value_list(f: dict, prompt_text: str, allowed: dict | None) -> dict | None:
    """Pass B, mechanical: a list is determined when every reference value is either an IFC
    allowed value for that property (so the schema supplies it) or appears in the request."""
    vals = enum_values(f.get("value"))
    if not vals:
        return None
    ps, bn = f.get("propertySet") or "", f.get("baseName") or ""
    if ps.startswith("RESTRICTION("):
        ps = (enum_values(ps) or [""])[0]
    known = [x.casefold() for x in ((allowed or {}).get(ps) or {}).get(bn, [])]
    from_schema = [v for v in vals if v.casefold() in known]
    from_text = [v for v in vals if mentions(prompt_text, v)]
    covered = {v for v in from_schema} | {v for v in from_text}
    extras = [v for v in vals if v not in covered]
    if not extras:
        return {"determined": True, "scope": "value",
                "reason": f"all {len(vals)} values recoverable ({len(from_schema)} from the IFC "
                          f"enumeration, {len(from_text)} stated in the request)"}
    return {"determined": False, "scope": "value",
            "reason": f"{len(extras)} of {len(vals)} values are neither IFC allowed values nor in the "
                      f"request ({', '.join(extras[:4])})"}


# Pass B readings for facets with no description in the source IDS. One line per case, written
# after reading the request text. Keyed by (item id, facet index).
READINGS = {
    ("IDS4ALL-Template_Example specifications.ids#2", i): (
        False, "the request only defines what a slab is; this property is never mentioned")
    for i in range(1, 9)
}
READINGS.update({
    ("IDS4ALL-Template_Example specifications.ids#17", i): (
        False, "the request states only the fire-rating requirement; this property is never mentioned")
    for i in (0, 2, 3, 4)
})
READINGS.update({
    ("IDS4ALL-Template_Example specifications.ids#18", 1): (
        False, "the request states only the fire-rating requirement; load bearing is never mentioned"),
    ("IDS_oma_input.ids#2", 1): (
        False, "the request asks for the storey name/number; floor elevation is never mentioned"),
})


def pass_b(item: dict, i: int, f: dict, prompt_text: str, described: set, allowed: dict | None):
    """Final verdict for one facet: (determined, scope, reason, method)."""
    if (i + 1) not in described:
        key = (item["id"], i)
        if key not in READINGS:
            raise SystemExit(f"no reading recorded for {key} — add it to READINGS before scoring")
        det, why = READINGS[key]
        return det, "facet", why, "B-read"
    v = judge_value_list(f, prompt_text, allowed)
    if v is not None:
        return v["determined"], "value", v["reason"], "B-mechanical"
    a = judge(f, prompt_text, True)                 # patterns, fixed values, bounds
    if a is None:
        return True, "value", "no value constraint to recover", "A-heuristic"
    return False, "value", a["reason"], "A-heuristic"


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="draft for all 185 items (default: the IFC-only items under study)")
    ap.add_argument("--graph-cache", default=str(RUNS_DIR / "spec_gemini-2.5-flash"),
                    help="run dir holding graph_psets.json, used to select IFC-only items")
    args = ap.parse_args(argv)
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(TESTSET_DIR / "spec_tasks.jsonl")
    if not args.all:
        psets = graph_psets(Path(args.graph_cache))
        if psets is None:
            raise SystemExit("graph needed to select IFC-only items (or pass --all)")
        tasks = [t for t in tasks if ifc_only(t, psets)]
    allowed = graph_allowed_values(Path(args.graph_cache))
    if allowed is None:
        raise SystemExit("graph needed for the value-list rule")
    print(f"annotating {len(tasks)} items")

    a_rows, b_rows, disagreements = [], [], []
    cache: dict = {}
    for t in tasks:
        src, _, spec_no = t["id"].partition("#")
        key = (src, spec_no)
        if key not in cache:
            cache[key] = described_indices(src, spec_no)
        described = cache[key]
        prompt_text = " \n".join(t["prompt"]["requirements"])
        for i, f in enumerate(t["target"]):
            a = judge(f, prompt_text, (i + 1) in described)
            a_det = a is None                        # pass A: flagged == undetermined
            if a is not None:
                a_rows.append({"id": t["id"], "facet_index": i, **a, "facet": facet_label(f),
                               "value": f.get("value"), "method": "A-heuristic"})
            det, scope, why, method = pass_b(t, i, f, prompt_text, described, allowed)
            if not det:
                b_rows.append({"id": t["id"], "facet_index": i, "determined": False, "scope": scope,
                               "reason": why, "facet": facet_label(f), "value": f.get("value"),
                               "method": method})
            if det != a_det:
                disagreements.append({"id": t["id"], "facet_index": i, "facet": facet_label(f),
                                      "pass_a": "determined" if a_det else "undetermined",
                                      "pass_b": "determined" if det else "undetermined",
                                      "reason_b": why})

    with open(DRAFT, "w", encoding="utf-8") as fh:
        for r in a_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(REVIEWED, "w", encoding="utf-8") as fh:
        for r in b_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_facets = sum(len(t["target"]) for t in tasks)
    agree = n_facets - len(disagreements)
    by_scope: dict = {}
    for r in b_rows:
        by_scope[r["scope"]] = by_scope.get(r["scope"], 0) + 1
    md = ["# Determinacy annotations (machine-made, not human-reviewed)", "",
          f"Items: {len(tasks)}. Target facets: {n_facets}.", "",
          f"- pass A (text heuristics) marked {len(a_rows)} facets undetermined",
          f"- pass B (final: mechanical value rule + author's reading) marked {len(b_rows)}: {by_scope}",
          f"- the passes agree on {agree}/{n_facets} facets ({100 * agree / n_facets:.0f}%)", "",
          "`scope=facet` drops the requirement from the relaxed reference; `scope=value` keeps the",
          "requirement and drops its value constraint.", "",
          "## Appendix: disagreements", ""]
    md += ([f"- {d['id']} facet {d['facet_index']} ({d['facet']}): A={d['pass_a']}, B={d['pass_b']} — {d['reason_b']}"
            for d in disagreements] or ["(none)"])
    md += ["", "## Pass B, undetermined facets", ""]
    for r in b_rows:
        md.append(f"- {r['id']} facet {r['facet_index']} — {r['facet']} — **{r['scope']}** "
                  f"[{r['method']}] — {r['reason']}")
    REVIEW_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"pass A: {len(a_rows)} undetermined | pass B: {len(b_rows)} {by_scope} | "
          f"agreement {agree}/{n_facets} ({100 * agree / n_facets:.0f}%)")
    print(f"-> {REVIEWED}\n-> {DRAFT}\n-> {REVIEW_MD}")


if __name__ == "__main__":
    main()
