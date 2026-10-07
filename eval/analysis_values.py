"""Value-field analysis and compact-mode checks (work order addendum §1, §5).

    python -m eval.analysis_values run5-rep1 run5-rep2 run5-rep3 --suffix _run5

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

The raw value comparison is exact string equality after the existing canonicalisation. The
normalised comparison added here is deliberately more forgiving, and is reported ALONGSIDE the
raw one, never instead of it:
  - case and surrounding whitespace ignored;
  - numbers compared as numbers (0.3 == 0.30);
  - enumerations compared as sets, so order does not matter;
  - a single simpleValue counts as equal to a one-item enumeration;
  - patterns are still compared as strings, because regex equivalence is undecidable in general.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from lxml import etree

from eval import score as S
from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks, safe_name

OUT = EVAL_DIR / "reports" / "v8"
ANN = EVAL_DIR / "annotations" / "determinacy.jsonl"
RNG = random.Random(20261007)


# --------------------------------------------------------------------------- normalisation
def _num(tok: str):
    try:
        return float(tok.replace(",", ".")) if re.fullmatch(r"-?\d+([.,]\d+)?", tok.strip()) else None
    except ValueError:
        return None


def _tok(tok: str):
    n = _num(tok)
    return n if n is not None else tok.strip().casefold()


def value_relation(ref: str | None, gen: str | None) -> str:
    """Describe how two values relate. Descriptive only — no metric depends on it."""
    a, b = normalise_value(ref), normalise_value(gen)
    if a == b:
        return "equal"
    if a is None or b is None:
        return "reference only" if b is None else "generated only"
    if a[0] == "set" and b[0] == "set":
        ra, rb = a[1], b[1]
        if rb < ra:
            return "generated is a subset (stricter: fewer values allowed)"
        if ra < rb:
            return "generated is a superset (more lenient)"
        return "overlapping" if ra & rb else "disjoint value lists"
    kinds = {a[0], b[0]}
    if kinds == {"set", "mixed"}:
        return "list versus pattern/bound"
    return f"different kinds ({a[0]} vs {b[0]})"


def normalise_value(v: str | None):
    """A comparable structure for a value, forgiving of form but not of content."""
    if v is None:
        return None
    v = v.strip()
    if not v.startswith("RESTRICTION("):
        return ("set", frozenset({_tok(v)}))                  # simpleValue == one-item enumeration
    members = S.restriction_members(v)
    enums = frozenset(_tok(x) for k, x in members if k == "enumeration")
    others = tuple(sorted((k, _tok(x)) for k, x in members if k != "enumeration"))
    if enums and not others:
        return ("set", enums)
    if not enums and not others:
        return ("empty",)
    return ("mixed", enums, others)


# --------------------------------------------------------------------------- matched pairs
def matched_pairs(runs: list[str]) -> pd.DataFrame:
    """One row per reference requirement that a candidate requirement matches by name."""
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    undet: dict = {}
    for line in open(ANN, encoding="utf-8"):
        r = json.loads(line)
        undet[(r["id"], r["facet_index"])] = r["scope"]
    rows = []
    for run in runs:
        for p in sorted((RUNS_DIR / run / "generated").glob("*.ids")):
            iid = next((k for k in tasks if safe_name(k) == p.stem), None)
            if iid is None:
                continue
            cand = S.parse_candidate(p)
            by: dict = {}
            for f in cand["requirements"]:
                by.setdefault(S.loose_key(f), []).append(f)
            for i, rf in enumerate(tasks[iid]["target"]):
                k = S.loose_key(rf)
                if k not in by or not by[k]:
                    continue
                cf = by[k].pop(0)
                rv_raw = S.canon_value(rf["facet"], "value", rf.get("value"))
                cv_raw = S.canon_value(cf["facet"], "value", cf.get("value"))
                rows.append({
                    "run": run, "id": iid, "facet_index": i, "facet": rf["facet"],
                    "key": " / ".join(str(x) for x in k[1:]),
                    "ref_value": rf.get("value"), "gen_value": cf.get("value"),
                    "ref_has_value": rv_raw is not None, "gen_has_value": cv_raw is not None,
                    "raw_agree": rv_raw == cv_raw,
                    "norm_agree": normalise_value(rf.get("value")) == normalise_value(cf.get("value")),
                    "value_relation": value_relation(rf.get("value"), cf.get("value")),
                    "ref_dataType": (rf.get("dataType") or "").upper() or None,
                    "gen_dataType": (cf.get("dataType") or "").upper() or None,
                    "dataType_agree": (rf.get("dataType") or "").upper() == (cf.get("dataType") or "").upper(),
                    "cardinality_agree": (rf.get("cardinality") or "required") == (cf.get("cardinality") or "required"),
                    "determinacy": undet.get((iid, i), "determined"),
                })
    return pd.DataFrame(rows)


def value_2x2(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rh in (True, False):
        for gh in (True, False):
            sub = df[(df.ref_has_value == rh) & (df.gen_has_value == gh)]
            rows.append({"reference has a value": rh, "generated has a value": gh,
                         "matched pairs": len(sub),
                         "raw agreements": int(sub.raw_agree.sum()),
                         "normalised agreements": int(sub.norm_agree.sum())})
    rows.append({"reference has a value": "TOTAL", "generated has a value": "",
                 "matched pairs": len(df), "raw agreements": int(df.raw_agree.sum()),
                 "normalised agreements": int(df.norm_agree.sum())})
    return pd.DataFrame(rows)


def field_table(df: pd.DataFrame) -> pd.DataFrame:
    """Every field with its own n, including the both-empty cases that the raw value row skips."""
    both_empty = int(((~df.ref_has_value) & (~df.gen_has_value)).sum())
    compared_v = len(df) - both_empty
    v = df[df.ref_has_value | df.gen_has_value]
    return pd.DataFrame([
        {"field": "name match (property set + property name)", "n": len(df),
         "agree": len(df), "rate": 1.0,
         "note": "by construction: the name is the matching key, so this is not a result"},
        {"field": "dataType", "n": len(df), "agree": int(df.dataType_agree.sum()),
         "rate": round(df.dataType_agree.mean(), 3), "note": ""},
        {"field": "cardinality", "n": len(df), "agree": int(df.cardinality_agree.sum()),
         "rate": round(df.cardinality_agree.mean(), 3), "note": ""},
        {"field": "value (raw, at least one side has one)", "n": compared_v,
         "agree": int(v.raw_agree.sum()), "rate": round(v.raw_agree.mean(), 3) if compared_v else None,
         "note": "exact string equality after canonicalisation"},
        {"field": "value (normalised, at least one side has one)", "n": compared_v,
         "agree": int(v.norm_agree.sum()), "rate": round(v.norm_agree.mean(), 3) if compared_v else None,
         "note": "case/whitespace, numeric, enumeration-as-set, simpleValue == one-item enumeration"},
        {"field": "value (both sides empty)", "n": both_empty, "agree": both_empty, "rate": 1.0,
         "note": "trivially equal; excluded from the two rows above"},
    ])


def by_determinacy(df: pd.DataFrame) -> pd.DataFrame:
    v = df[df.ref_has_value | df.gen_has_value]
    rows = []
    for det, sub in v.groupby(v.determinacy.map(lambda d: "not derivable" if d == "value" else d)):
        rows.append({"determinacy of the reference value": det, "matched pairs": len(sub),
                     "raw agreements": int(sub.raw_agree.sum()),
                     "normalised agreements": int(sub.norm_agree.sum()),
                     "normalised rate": round(sub.norm_agree.mean(), 3)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- verbatim quotes
def _readable(el) -> str:
    """Serialise one element without the namespace declarations, which swamp a short quote."""
    xml = etree.tostring(el, pretty_print=True, encoding="unicode")
    xml = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', "", xml)
    return re.sub(r"\s+", " ", xml).strip()


def facet_xml(path: Path, pset: str | None, base: str | None, attr: str | None) -> str:
    """The exact XML element for one facet, as it appears in the file."""
    try:
        tree = etree.parse(str(path))
    except Exception:
        return ""
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el).localname
        if local == "property" and pset:
            got_ps = el.findtext(f"{{{S.NS_IDS}}}propertySet/{{{S.NS_IDS}}}simpleValue")
            got_bn = el.findtext(f"{{{S.NS_IDS}}}baseName/{{{S.NS_IDS}}}simpleValue")
            if got_ps == pset and got_bn == base:
                return _readable(el)
        if local == "attribute" and attr:
            got = el.findtext(f"{{{S.NS_IDS}}}name/{{{S.NS_IDS}}}simpleValue")
            if got == attr:
                return _readable(el)
    return ""


def quote_disagreements(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    pool = df[(df.ref_has_value | df.gen_has_value) & (~df.norm_agree)]
    picks = RNG.sample(range(len(pool)), min(n, len(pool)))
    rows = []
    for idx in picks:
        r = pool.iloc[idx]
        tgt = tasks[r.id]["target"][r.facet_index]
        pset = tgt.get("propertySet")
        if pset and pset.startswith("RESTRICTION("):
            pset = (re.findall(r"enumeration=([^,)]+)", pset) or [None])[0]
        ref_xml = facet_xml(RUNS_DIR / r.run / "reference" / f"{safe_name(r.id)}.ids",
                            pset, tgt.get("baseName"), tgt.get("name"))
        gen_xml = facet_xml(RUNS_DIR / r.run / "generated" / f"{safe_name(r.id)}.ids",
                            pset, tgt.get("baseName"), tgt.get("name"))
        rows.append({"run": r.run, "id": r.id, "facet": r.key,
                     "determinacy": "not derivable" if r.determinacy == "value" else r.determinacy,
                     "reference_xml": ref_xml, "generated_xml": gen_xml})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- unmatched
def unmatched(runs: list[str]) -> pd.DataFrame:
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    rows = []
    for run in runs:
        for p in sorted((RUNS_DIR / run / "generated").glob("*.ids")):
            iid = next((k for k in tasks if safe_name(k) == p.stem), None)
            if iid is None:
                continue
            cand = S.parse_candidate(p)
            by: dict = {}
            for f in cand["requirements"]:
                by.setdefault(S.loose_key(f), []).append(f)
            cand_props = [f for f in cand["requirements"] if f["facet"] == "property"]
            for i, rf in enumerate(tasks[iid]["target"]):
                k = S.loose_key(rf)
                if k in by and by[k]:
                    by[k].pop(0)
                    continue
                kind = "absent entirely"
                if rf["facet"] == "property":
                    ps, bn = rf.get("propertySet"), rf.get("baseName")
                    if any(c.get("baseName") == bn for c in cand_props):
                        kind = "present under a different property set"
                    elif any(c.get("propertySet") == ps for c in cand_props):
                        kind = "property set present, different property name"
                rows.append({"run": run, "id": iid, "facet_index": i, "facet": rf["facet"],
                             "reference": f"{rf.get('propertySet') or ''}.{rf.get('baseName') or rf.get('name') or ''}",
                             "kind": kind})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- §5 compact checks
def compact_checks() -> pd.DataFrame:
    """Does compact mode preserve the corrected IFC type, and are any allowed values prose-only?"""
    from aec_kg.main_orchestrator import compact_class_result
    from aec_kg.neuro_agent import get_class_requirements
    rows = []
    r = get_class_requirements("IfcWall")
    comp = compact_class_result(r)
    full_props = {p["code"]: p for p in r["property_sets"]["Pset_WallCommon"]["properties"]}
    comp_props = {p["code"]: p for p in comp["property_sets"]["Pset_WallCommon"]}
    kept = [c for c in full_props if full_props[c].get("ifc_type") and comp_props.get(c, {}).get("ifc_type")]
    rows.append({"check": "ifc_type survives compact mode (Pset_WallCommon)",
                 "result": f"{len(kept)} of {sum(1 for c in full_props if full_props[c].get('ifc_type'))} kept",
                 "detail": "ifc_type is parsed at ingestion and stored on the node, so compact mode "
                           "cannot undo the dataType fix; it only drops definition/description"})
    rows.append({"check": "bSDD coarse data_type also still present",
                 "result": "yes" if any(p.get("data_type") for p in comp_props.values()) else "no",
                 "detail": "kept so the model can see both, as in full mode"})
    # allowed values that exist only in prose
    data = json.load(open(EVAL_DIR.parent / "data" / "ifc-4.3.json", encoding="utf-8"))
    prose_only, n_no_av = [], 0
    pat = re.compile(r"\b(one of|shall be either|values are|permitted values)\b", re.I)
    for p in data["Properties"]:
        if p.get("AllowedValues"):
            continue
        n_no_av += 1
        text = f"{p.get('Description') or ''} {p.get('Definition') or ''}"
        if pat.search(text):
            prose_only.append(p["Code"])
    rows.append({"check": "allowed values that appear only in prose",
                 "result": f"{len(prose_only)} of {n_no_av} properties without a structured list",
                 "detail": "examples: " + ", ".join(prose_only[:6]) if prose_only else "none found"})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    df = matched_pairs(a.runs)
    df.to_csv(OUT / f"v1_matched_pairs{a.suffix}.csv", index=False)

    t = value_2x2(df)
    t.to_csv(OUT / f"v2_value_2x2{a.suffix}.csv", index=False)
    print("=== value field: 2x2 over matched requirements")
    print(t.to_string(index=False))

    ft = field_table(df)
    ft.to_csv(OUT / f"v3_field_table{a.suffix}.csv", index=False)
    print("\n=== field table with n for every field")
    print(ft.to_string(index=False))

    rel = (df[df.ref_has_value | df.gen_has_value].value_relation.value_counts()
           .rename_axis("relation").reset_index(name="pairs"))
    rel.to_csv(OUT / f"v8_value_relations{a.suffix}.csv", index=False)
    print("\n=== how the two values relate (descriptive)")
    print(rel.to_string(index=False))

    bd = by_determinacy(df)
    bd.to_csv(OUT / f"v4_value_by_determinacy{a.suffix}.csv", index=False)
    print("\n=== value agreement split by determinacy")
    print(bd.to_string(index=False))

    q = quote_disagreements(df)
    q.to_csv(OUT / f"v5_value_disagreements_verbatim{a.suffix}.csv", index=False)
    print(f"\n=== {len(q)} verbatim disagreeing pairs -> v5_value_disagreements_verbatim{a.suffix}.csv")
    for _, r in q.head(3).iterrows():
        print(f"  {r.id[-26:]} {r.facet} [{r.determinacy}]")
        print(f"    reference: {' '.join(r.reference_xml.split())[:120]}")
        print(f"    generated: {' '.join(r.generated_xml.split())[:120]}")

    um = unmatched(a.runs)
    um.to_csv(OUT / f"v6_unmatched_reference{a.suffix}.csv", index=False)
    print("\n=== unmatched reference requirements")
    print(um.kind.value_counts().to_string())
    print(f"  total unmatched: {len(um)}")

    cc = compact_checks()
    cc.to_csv(OUT / f"v7_compact_checks{a.suffix}.csv", index=False)
    print("\n=== compact-mode checks")
    for _, r in cc.iterrows():
        print(f"  {r.check}: {r.result}")
        print(f"      {r.detail}")
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
