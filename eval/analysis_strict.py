"""Strict-headline breakdown and no-file analysis (addendum §3, §4).

    python -m eval.analysis_strict run5-rep1 run5-rep2 run5-rep3 --suffix _run5

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

Direction labels, one sentence each:
  under_strict      the generated IDS passes objects the reference fails (too lenient)
  over_strict       the generated IDS fails objects the reference passes (too demanding)
  over_applicable   it applies to objects the reference ignores
  under_applicable  it ignores objects the reference checks
  no_file           no IDS was produced, so there is nothing to execute (its own category,
                    not a direction: an empty specification trivially ignores everything)
  equivalent        identical verdict on every test object
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from eval import score as S
from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks, safe_name

OUT = EVAL_DIR / "reports" / "v8"
ANN = EVAL_DIR / "annotations" / "determinacy.jsonl"
LABELS = {
    "under_strict": "generated passes objects the reference fails (too lenient)",
    "over_strict": "generated fails objects the reference passes (too demanding)",
    "over_applicable": "applies to objects the reference ignores",
    "under_applicable": "ignores objects the reference checks",
    "equivalent": "identical verdict on every test object",
    "no_file": "no IDS produced, nothing to execute",
    "witness_unverified": "the test model could not be verified against its own reference",
}


def annotations() -> dict:
    out: dict = {}
    for line in open(ANN, encoding="utf-8"):
        r = json.loads(line)
        out[(r["id"], r["facet_index"])] = r["scope"]
    return out


def field_causes(iid: str, run: str, tasks: dict, ann: dict) -> list[str]:
    """Field-level causes for one item-run, from the text comparison."""
    p = RUNS_DIR / run / "generated" / f"{safe_name(iid)}.ids"
    if not p.exists():
        return ["no file"]
    cand = S.parse_candidate(p)
    by: dict = {}
    for f in cand["requirements"]:
        by.setdefault(S.loose_key(f), []).append(f)
    causes = Counter()
    for i, rf in enumerate(tasks[iid]["target"]):
        k = S.loose_key(rf)
        if k not in by or not by[k]:
            causes["missing requirement"] += 1
            continue
        cf = by[k].pop(0)
        rv = S.canon_value(rf["facet"], "value", rf.get("value"))
        cv = S.canon_value(cf["facet"], "value", cf.get("value"))
        if rv is not None and cv is None:
            causes["value list not derivable" if ann.get((iid, i)) == "value" else "missing value"] += 1
        elif rv != cv and (rv is not None or cv is not None):
            causes["value list not derivable" if ann.get((iid, i)) == "value" else "wrong value"] += 1
        if (rf.get("dataType") or "").upper() != (cf.get("dataType") or "").upper():
            causes["wrong type"] += 1
    causes["extra requirement"] += sum(len(v) for v in by.values())
    return [c for c, n in causes.most_common() if n]


def breakdown(runs: list[str], relaxed: bool) -> pd.DataFrame:
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    ann = annotations()
    suffix = "_relaxed" if relaxed else ""
    rows = []
    for run in runs:
        d = pd.read_csv(RUNS_DIR / run / f"scores{suffix}.csv")
        d = d[d.ifc_only == 1]
        for _, r in d.iterrows():
            if pd.isna(r.wit_outcome_equiv):
                continue
            no_file = r.status != "ok"
            direction = "no_file" if no_file else ("equivalent" if r.wit_outcome_equiv else r.wit_direction)
            causes = field_causes(r.id, run, tasks, ann)
            rows.append({"run": run, "id": r.id, "scoring": "determined-only" if relaxed else "strict",
                         "requirements": r.n_target, "status": r.status,
                         "passes": int(r.wit_outcome_equiv), "direction": direction,
                         "s2": round(r.wit_s2, 3) if pd.notna(r.wit_s2) else None,
                         "primary_field_cause": causes[0] if causes else "none",
                         "all_field_causes": "; ".join(causes) or "none"})
    return pd.DataFrame(rows)


def crosstab(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df.passes == 0]
    ct = pd.crosstab(sub.direction, sub.primary_field_cause)
    return ct.reset_index()


def crosstab_all(df: pd.DataFrame) -> pd.DataFrame:
    """Every cause counted, not only the most frequent one per item-run. An item can appear in
    several columns, so rows do not sum to the failure count."""
    sub = df[df.passes == 0]
    rows = []
    for direction, g in sub.groupby("direction"):
        row = {"direction": direction, "item_runs": len(g)}
        for _, r in g.iterrows():
            for c in str(r.all_field_causes).split("; "):
                if c and c != "none":
                    row[c] = row.get(c, 0) + 1
        rows.append(row)
    return pd.DataFrame(rows).fillna(0)


def per_facet_evidence(runs: list[str], tasks: dict, ann: dict) -> pd.DataFrame:
    """One row per reference facet of every failing item-run: what the reference asked and what
    the generated file said."""
    rows = []
    for run in runs:
        d = pd.read_csv(RUNS_DIR / run / "scores.csv")
        d = d[(d.ifc_only == 1) & (d.wit_outcome_equiv == 0)]
        for _, r in d.iterrows():
            p = RUNS_DIR / run / "generated" / f"{safe_name(r.id)}.ids"
            cand = S.parse_candidate(p) if p.exists() else {"requirements": []}
            by: dict = {}
            for f in cand["requirements"]:
                by.setdefault(S.loose_key(f), []).append(f)
            for i, rf in enumerate(tasks[r.id]["target"]):
                k = S.loose_key(rf)
                cf = by[k].pop(0) if (k in by and by[k]) else None
                rows.append({
                    "run": run, "id": r.id, "facet_index": i, "facet": rf["facet"],
                    "reference_name": f"{rf.get('propertySet') or ''}.{rf.get('baseName') or rf.get('name') or ''}".strip("."),
                    "matched": cf is not None,
                    "reference_value": rf.get("value"), "generated_value": cf.get("value") if cf else None,
                    "reference_dataType": rf.get("dataType"), "generated_dataType": cf.get("dataType") if cf else None,
                    "reference_cardinality": rf.get("cardinality") or "required",
                    "generated_cardinality": (cf.get("cardinality") or "required") if cf else None,
                    "determinacy": ann.get((r.id, i), "determined"),
                    "item_direction": r.wit_direction,
                })
            for key, left in by.items():
                for cf in left:
                    rows.append({"run": run, "id": r.id, "facet_index": None, "facet": cf["facet"],
                                 "reference_name": None, "matched": False,
                                 "reference_value": None, "generated_value": cf.get("value"),
                                 "reference_dataType": None, "generated_dataType": cf.get("dataType"),
                                 "reference_cardinality": None,
                                 "generated_cardinality": cf.get("cardinality") or "required",
                                 "determinacy": "extra requirement (no reference facet)",
                                 "item_direction": r.wit_direction})
    return pd.DataFrame(rows)


def label_methods() -> pd.DataFrame:
    rows = [json.loads(l) for l in open(ANN, encoding="utf-8")]
    out = []
    for scope in ("value", "facet"):
        sub = [r for r in rows if r["scope"] == scope]
        by = Counter(r["method"] for r in sub)
        out.append({"scope": scope, "labels": len(sub),
                    "from the mechanical rule": by.get("B-mechanical", 0),
                    "from the text heuristic": by.get("A-heuristic", 0),
                    "from the author's reading": by.get("B-read", 0)})
    return pd.DataFrame(out)


def nofile_detail(runs: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One mutually exclusive cause per no-file item-run, with the model's own words."""
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    ann = annotations()
    rows, attempts_rows = [], []
    for run in runs:
        for line in open(RUNS_DIR / run / "log.jsonl", encoding="utf-8"):
            j = json.loads(line)
            if j["status"] == "ok":
                continue
            gen_calls = [c for c in (j.get("tool_calls") or []) if c["tool"] == "generate_ids"]
            n = len(gen_calls)
            ans = (j.get("answer") or "")
            if j["status"] == "budget_exceeded":
                cause = "stopped by the per-item budget"
            elif n == 0 and "?" in ans:
                cause = "asked a clarifying question (never called the generator)"
            elif n == 0:
                cause = "declined without calling the generator"
            else:
                cause = f"every generator attempt rejected ({n})"
            tgt = tasks[j["id"]]["target"]
            undet = [i for i in range(len(tgt)) if (j["id"], i) in ann]
            question = next((s.strip() for s in ans.replace("\n", " ").split(". ") if "?" in s), "")
            rows.append({"run": run, "id": j["id"], "status": j["status"], "cause": cause,
                         "generator_attempts": n, "requirements": len(tgt),
                         "undetermined_facets": len(undet),
                         "all_requirements_undetermined": len(undet) == len(tgt),
                         "question_asked": question[:300],
                         "answer_opening": ans[:200].replace("\n", " ")})
            errs = []
            for idx, c in enumerate(gen_calls, 1):
                res = c["result"]
                first = (res.get("validation_errors") or res.get("xsd_errors") or [res.get("error")])[0]
                errs.append(str(first)[:150])
                attempts_rows.append({"run": run, "id": j["id"], "attempt": idx,
                                      "first_error": str(first)[:200]})
            if errs:
                attempts_rows.append({"run": run, "id": j["id"], "attempt": "ALL",
                                      "first_error": f"same error every attempt: {len(set(errs)) == 1}"})
    return pd.DataFrame(rows), pd.DataFrame(attempts_rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    print("=== direction labels")
    for k, v in LABELS.items():
        print(f"  {k:<20} {v}")

    frames = []
    for relaxed in (False, True):
        df = breakdown(a.runs, relaxed)
        frames.append(df)
        label = "determined-only" if relaxed else "strict"
        df.to_csv(OUT / f"s1_item_runs_{label.replace('-', '_')}{a.suffix}.csv", index=False)
        print(f"\n=== {label}: denominators")
        print(f"  item-runs scored: {len(df)}  ({df.id.nunique()} distinct items x {len(a.runs)} repeats)")
        print(f"  pass: {int(df.passes.sum())}   fail: {int((df.passes == 0).sum())}")
        print(f"  of the failures, no-file: {int(((df.passes == 0) & (df.direction == 'no_file')).sum())}")
        print(f"  direction breakdown:")
        for k, v in df[df.passes == 0].direction.value_counts().items():
            print(f"    {k:<28}{v}")
        ct = crosstab(df)
        ct.to_csv(OUT / f"s2_direction_x_cause_{label.replace('-', '_')}{a.suffix}.csv", index=False)
        print(f"  direction x primary field-level cause:")
        print(ct.to_string(index=False))
        cta = crosstab_all(df)
        cta.to_csv(OUT / f"s2b_direction_x_all_causes_{label.replace('-', '_')}{a.suffix}.csv", index=False)
        print(f"  direction x every cause present (an item-run can appear in several columns):")
        print(cta.to_string(index=False))

    lm = label_methods()
    lm.to_csv(OUT / f"s5_annotation_methods{a.suffix}.csv", index=False)
    print("\n=== do the determinacy labels follow mechanically?")
    print(lm.to_string(index=False))
    print("  the value labels are NOT all mechanical: the enumeration rule produced 23 of 31;")
    print("  the other 8 (patterns, fixed values, one numeric bound) came from the text heuristic.")

    ev = per_facet_evidence(a.runs, {t["id"]: t for t in load_tasks(SPEC_TASKS)}, annotations())
    ev.to_csv(OUT / f"s6_per_facet_evidence{a.suffix}.csv", index=False)
    print(f"\n=== per-facet evidence: {len(ev)} facet rows across the failing item-runs "
          f"-> s6_per_facet_evidence{a.suffix}.csv")

    nf, att = nofile_detail(a.runs)
    nf.to_csv(OUT / f"s3_nofile_items{a.suffix}.csv", index=False)
    att.to_csv(OUT / f"s4_nofile_attempts{a.suffix}.csv", index=False)
    total_runs = len(frames[0])
    scored_nofile = int((frames[0].direction == "no_file").sum())
    print(f"\n=== no-file: {len(nf)} item-runs in the logs; {scored_nofile} of them fall inside the "
          f"{total_runs} scored item-runs ({100 * scored_nofile / max(total_runs, 1):.0f}%)")
    print(f"  the other {len(nf) - scored_nofile} are items whose test model could not be verified, "
          f"so they are excluded from the scored set entirely")
    print(nf.cause.value_counts().to_string())
    print("  determinacy of the no-file items:")
    for _, r in nf.iterrows():
        print(f"    {r.id[-30:]:<32} {r.undetermined_facets}/{r.requirements} facets undetermined"
              f"{'  (all of them)' if r.all_requirements_undetermined else ''}")
    qs = nf[nf.question_asked.str.len() > 0]
    if len(qs):
        print("  questions the model asked:")
        for _, r in qs.head(6).iterrows():
            print(f"    {r.id[-26:]}: \"{r.question_asked[:150]}\"")
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
