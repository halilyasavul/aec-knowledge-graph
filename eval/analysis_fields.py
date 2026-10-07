"""Field-level text scores, strict-headline evidence, and the no-file breakdown (v8 §1-§3).

    python -m eval.analysis_fields run5-rep1 run5-rep2 run5-rep3 [...]

Read-only over run directories; no model calls. Writes t7/t8/t9 CSVs to eval/reports/v7/.

Why field level: a single facet-match score answers "is this requirement exactly right?" and
hides which part was wrong. Here each reference requirement is first MATCHED to a candidate
requirement by name, and then the remaining fields are compared one at a time. Unmatched
requirements are counted separately, so the matched comparisons are not inflated by them.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import ifcopenshell
import pandas as pd

from eval import score as S
from eval import witness
from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks, safe_name

OUT = EVAL_DIR / "reports" / "v7"
FIELDS = ("propertySet", "baseName", "name", "dataType", "value", "cardinality")


def _norm(f: dict, field: str):
    if field == "cardinality":
        return (f.get("cardinality") or "required").strip().lower()
    return S.canon_value(f["facet"], field, f.get(field))


def field_rows(runs: list[str]) -> pd.DataFrame:
    """Per-field agreement over reference requirements matched to a candidate requirement."""
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    agg: dict = {}
    for run in runs:
        gen = RUNS_DIR / run / "generated"
        counts = Counter()
        for p in sorted(gen.glob("*.ids")):
            iid = next((k for k in tasks if safe_name(k) == p.stem), None)
            if iid is None:
                continue
            cand = S.parse_candidate(p)
            ref_facets = tasks[iid]["target"]
            cand_by_key: dict = {}
            for f in cand["requirements"]:
                cand_by_key.setdefault(S.loose_key(f), []).append(f)
            for rf in ref_facets:
                k = S.loose_key(rf)
                counts["reference requirements"] += 1
                if k in cand_by_key and cand_by_key[k]:
                    cf = cand_by_key[k].pop(0)
                    counts["matched by name"] += 1
                    for field in FIELDS:
                        if rf.get(field) is None and cf.get(field) is None and field != "cardinality":
                            continue
                        counts[f"field {field}: compared"] += 1
                        if _norm(rf, field) == _norm(cf, field):
                            counts[f"field {field}: agree"] += 1
                    rv, cv = _norm(rf, "value"), _norm(cf, "value")   # where values disagree
                    if rv is not None or cv is not None:
                        counts["value: " + ("identical" if rv == cv else
                                            "reference has one, generated none" if cv is None else
                                            "generated added one" if rv is None else
                                            "both present, different")] += 1
                else:
                    counts["unmatched (missing requirement)"] += 1
            counts["extra candidate requirements"] += sum(len(v) for v in cand_by_key.values())
        agg[run] = counts
    rows = []
    keys = sorted({k for c in agg.values() for k in c})
    for k in keys:
        row = {"measure": k}
        for run, c in agg.items():
            row[run] = c.get(k, 0)
        rows.append(row)
    df = pd.DataFrame(rows)
    # add agreement rates per field, averaged over runs
    rate_rows = []
    for field in FIELDS:
        comp = sum(agg[r].get(f"field {field}: compared", 0) for r in runs)
        ag = sum(agg[r].get(f"field {field}: agree", 0) for r in runs)
        if comp:
            rate_rows.append({"field": field, "compared": comp, "agree": ag,
                              "agreement_rate": round(ag / comp, 3)})
    matched = sum(agg[r].get("matched by name", 0) for r in runs)
    refs = sum(agg[r].get("reference requirements", 0) for r in runs)
    extra = sum(agg[r].get("extra candidate requirements", 0) for r in runs)
    rate_rows.append({"field": "— name match (denominator for the rows above)", "compared": refs,
                      "agree": matched, "agreement_rate": round(matched / refs, 3) if refs else None})
    rate_rows.append({"field": "— extra candidate requirements", "compared": None, "agree": extra,
                      "agreement_rate": None})
    for k in ("identical", "reference has one, generated none", "generated added one",
              "both present, different"):
        n = sum(agg[r].get("value: " + k, 0) for r in runs)
        rate_rows.append({"field": f"   value breakdown — {k}", "compared": None, "agree": n,
                          "agreement_rate": None})
    return df, pd.DataFrame(rate_rows)


def evidence_rows(runs: list[str], relaxed: bool = False) -> pd.DataFrame:
    """For every item that fails the strict headline, the object where the two disagree."""
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    suffix = "_relaxed" if relaxed else ""
    rows = []
    for run in runs:
        d = pd.read_csv(RUNS_DIR / run / f"scores{suffix}.csv")
        d = d[d.ifc_only == 1]
        for _, r in d[d.wit_outcome_equiv == 0].iterrows():
            name = safe_name(r.id)
            wit_dir = RUNS_DIR / run / ("witness" + suffix)
            model_path, meta_path = wit_dir / f"{name}.ifc", wit_dir / f"{name}.json"
            ref_path = RUNS_DIR / run / ("reference" + suffix) / f"{name}.ids"
            cand_path = RUNS_DIR / run / "generated" / f"{name}.ids"
            evidence = reason = None
            if model_path.exists() and cand_path.exists():
                m = ifcopenshell.open(str(model_path))
                labels = json.loads(meta_path.read_text())["labels"]
                ref_x, cand_x = S.execute(ref_path, m, False), S.execute(cand_path, m, False)
                rv, cv = S.verdicts(labels, ref_x), S.verdicts(labels, cand_x)
                diff = [lab for lab in rv if rv[lab] != cv.get(lab, "n/a")]
                if diff:
                    lab = sorted(diff)[0]
                    evidence = f"{lab}: reference {rv[lab]}, generated {cv.get(lab, 'n/a')}"
                    pool = cand_x["reasons"] if cv.get(lab) == "fail" else ref_x["reasons"]
                    reason = next(iter(sorted(set(pool))), None)
            rows.append({"run": run, "id": r.id, "requirements": r.n_target,
                         "s2": round(r.wit_s2, 3) if pd.notna(r.wit_s2) else None,
                         "direction": r.wit_direction, "evidence_object": evidence,
                         "checker_reason": (reason or "")[:160],
                         "diverging_variants": str(r.get("wit_diverging"))[:100]})
    return pd.DataFrame(rows)


def nofile_rows(runs: list[str]) -> pd.DataFrame:
    rows = []
    for run in runs:
        log = RUNS_DIR / run / "log.jsonl"
        for line in open(log, encoding="utf-8"):
            j = json.loads(line)
            if j["status"] == "ok":
                continue
            attempts = (j.get("retries") or {}).get("generate_ids_attempts", 0)
            ans = (j.get("answer") or "").lower()
            if j["status"] == "budget_exceeded":
                kind = "stopped by the per-item budget"
            elif attempts == 0 and any(w in ans for w in ("could you", "please specify", "need a bit more",
                                                          "what specific", "clarify", "does not specify")):
                kind = "asked for clarification instead of answering"
            elif attempts == 0:
                kind = "never called the generator"
            else:
                kind = f"generator rejected every attempt ({attempts} tries)"
            rows.append({"run": run, "id": j["id"], "status": j["status"], "kind": kind,
                         "generate_attempts": attempts,
                         "last_error": str(j.get("error"))[:120],
                         "answer_opening": (j.get("answer") or "")[:140].replace("\n", " ")})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+", help="run directory names under eval/runs/")
    ap.add_argument("--suffix", default="", help="tag for the output files, e.g. _run6")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    raw, rates = field_rows(a.runs)
    raw.to_csv(OUT / f"t7_field_counts{a.suffix}.csv", index=False)
    rates.to_csv(OUT / f"t7_field_agreement{a.suffix}.csv", index=False)
    print("=== 1. FIELD-LEVEL TEXT SCORES (matched comparisons)")
    print("  note: propertySet/baseName/name are the matching key, so their 1.000 is by construction,")
    print("  not a result. The informative rows are dataType, cardinality and the value breakdown.")
    print(rates.to_string(index=False))

    ev = evidence_rows(a.runs)
    ev.to_csv(OUT / f"t8_strict_evidence{a.suffix}.csv", index=False)
    print("\n=== 2. STRICT HEADLINE — why each failing item fails")
    print(ev.direction.value_counts().to_string())
    print(f"  item-runs failing strict: {len(ev)}; distinct items: {ev.id.nunique()}")
    for _, r in ev.head(6).iterrows():
        print(f"    {r.id[-30:]:<32} {str(r.evidence_object)[:62]:<64} {r.checker_reason[:50]}")

    nf = nofile_rows(a.runs)
    nf.to_csv(OUT / f"t9_nofile{a.suffix}.csv", index=False)
    print("\n=== 3. NO-FILE BREAKDOWN")
    if len(nf):
        print(nf.kind.value_counts().to_string())
        print(f"  distinct items: {nf.id.nunique()} over {len(a.runs)} run(s)")
    else:
        print("  every item produced a file")
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
