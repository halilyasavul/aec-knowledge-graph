"""Export every number the v5 report quotes, as JSON, so the document cannot drift from the data.

    python -m eval.summary <run_dir> [<run_dir> ...] -o eval/reports/report_data.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from eval import report as rep
from eval.common import RUNS_DIR, SPEC_TASKS, graph_psets, ifc_only, load_tasks, safe_name


def filter_stats() -> dict:
    tasks = load_tasks(SPEC_TASKS)
    psets = graph_psets(RUNS_DIR / "spec_gemini-2.5-flash")
    keep = [t for t in tasks if ifc_only(t, psets)]
    return {"harvested": len(tasks), "usable": len(keep), "excluded": len(tasks) - len(keep),
            "by_source": Counter(t["source"] for t in keep).most_common(),
            "bands": {b: sum(1 for t in keep if rep.band_of(len(t["target"])) == b) for b in rep.BANDS}}


SCORES_FILE = "scores.csv"


def run_stats(run: Path) -> dict:
    r = rep.load(run, SCORES_FILE)
    df, logs = r["df"], r["logs"]
    m = rep.metrics(df)
    guards = Counter()
    for x in logs.values():
        guards.update(x.get("guards_fired") or {})
    ext = df[df.wit_outcome_equiv.notna()] if "wit_outcome_equiv" in df else df.iloc[0:0]
    nc = ext[ext.loose_f1 == 1.0]
    other = ext[ext.loose_f1 < 1.0]
    bands = {}
    for b in rep.BANDS:
        sub = df[df.band == b] if "band" in df else df.iloc[0:0]
        se = sub[sub.wit_outcome_equiv.notna()] if len(sub) else sub
        if len(sub):
            bands[b] = {"items": len(sub), "s1": [int(se.wit_outcome_equiv.sum()), len(se)],
                        "s2": _f(se.wit_s2.mean()), "enforce": _f(se.wit_enforce.mean()),
                        "false_reject": _f(se.wit_false_reject.mean()), "facet_f1": _f(sub.facet_f1.mean())}
    errs = {c[4:]: int(df[c].sum()) for c in df.columns if c.startswith("err_") and df[c].sum()}
    return {
        "name": run.name, "fixes": r["meta"].get("fixes"),
        "items": m["items"], "with_file": m["with_file"], "testable": m["testable"],
        "s1": list(m["S1"]), "s2": _f(m["S2"]), "s2_ref": _f(m["S2_ref"]), "s2_cand": _f(m["S2_cand"]),
        "enforce": _f(m["enforce"]), "false_reject": _f(m["false_reject"]),
        "app_out": _f(m["app_out"]), "app_in": _f(m["app_in"]),
        "facet_f1_micro": _f(m["facet_f1_micro"]), "facet_f1_macro": _f(m["facet_f1_macro"]),
        "names_correct": list(m["names_correct"]),
        "guards": dict(guards), "errors": errs, "bands": bands,
        "item_ids": list(df.id),
        "provenance": {c: int(df[c].sum()) for c in df.columns
                       if c.startswith("dt_") and df[c].sum()},
        "no_file": int((df.status != "ok").sum()),
        "gen_attempts": _f(pd.Series([x.get("retries", {}).get("generate_ids_attempts", 0)
                                     for x in logs.values()]).mean()) if logs else None,
        "psets_dropped": (sum(len(x.get("property_sets_dropped") or []) for x in logs.values())
                          if any("property_sets_dropped" in x for x in logs.values()) else None),
        "cost_per_item": _f(pd.Series([x["cost_usd"] for x in logs.values()]).mean()) if logs else None,
        "seconds_per_item": _f(pd.Series([x["wall_ms"] / 1000 for x in logs.values()]).mean()) if logs else None,
        "hypothesis": {
            "names_correct_testable": len(nc),
            "names_correct_s1": [int(nc.wit_outcome_equiv.sum()), len(nc)],
            "names_correct_s2": _f(nc.wit_s2.mean()), "names_correct_enforce": _f(nc.wit_enforce.mean()),
            "other_s1": [int(other.wit_outcome_equiv.sum()), len(other)], "other_s2": _f(other.wit_s2.mean()),
            "divergent_though_named": [
                {"id": row.id, "s2": _f(row.wit_s2), "direction": str(row.get("wit_direction"))}
                for _, row in nc.iterrows() if not row.wit_outcome_equiv],
            "distinct_facet_f1": int(ext.facet_f1.round(4).nunique()) if len(ext) else 0,
        },
    }


def _f(x, dp=3):
    return None if x is None or (isinstance(x, float) and pd.isna(x)) else round(float(x), dp)


NUMERIC = ["s2_ref", "s2", "s2_cand", "enforce", "false_reject", "app_out", "app_in",
           "facet_f1_micro", "facet_f1_macro"]


def cell_stats(runs: list[dict], name: str, det: dict | None = None) -> dict:
    """Aggregate repeats of one 2x2 cell: mean and min-max for every metric."""
    out = {"cell": name, "repeats": len(runs), "fixes": runs[0]["fixes"],
           "items": runs[0]["items"]}
    for k in NUMERIC:
        vals = [r[k] for r in runs if r.get(k) is not None]
        out[k] = {"mean": round(sum(vals) / len(vals), 3), "min": round(min(vals), 3),
                  "max": round(max(vals), 3)} if vals else None
    for k in ("s1", "names_correct"):
        num = [r[k][0] for r in runs]
        den = [r[k][1] for r in runs]
        out[k] = {"mean": round(sum(num) / len(num), 2), "min": min(num), "max": max(num),
                  "of": round(sum(den) / len(den), 1)}
    for k in ("with_file", "testable", "no_file"):
        vals = [r[k] for r in runs]
        out[k] = {"mean": round(sum(vals) / len(vals), 1), "min": min(vals), "max": max(vals)}
    errs: dict = {}
    for r in runs:
        for e, n in r["errors"].items():
            errs.setdefault(e, []).append(n)
    out["errors"] = {e: round(sum(v) / len(runs), 1) for e, v in errs.items()}
    prov: dict = {}
    for r in runs:
        for e, n in (r.get("provenance") or {}).items():
            prov.setdefault(e, []).append(n)
    out["provenance"] = {e: round(sum(v) / len(runs), 1) for e, v in prov.items()}
    hyp = [r["hypothesis"] for r in runs]
    out["hypothesis"] = {
        "names_correct_testable": round(sum(h["names_correct_testable"] for h in hyp) / len(hyp), 1),
        "names_correct_s1": [sum(h["names_correct_s1"][0] for h in hyp), sum(h["names_correct_s1"][1] for h in hyp)],
        "names_correct_s2": _f(_avg([h["names_correct_s2"] for h in hyp])),
        "other_s1": [sum(h["other_s1"][0] for h in hyp), sum(h["other_s1"][1] for h in hyp)],
        "other_s2": _f(_avg([h["other_s2"] for h in hyp])),
        "distinct_facet_f1": max(h["distinct_facet_f1"] for h in hyp),
    }
    if det:
        out["identical_across_repeats"] = det
    return out


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("-o", "--out", default="eval/reports/report_data.json")
    ap.add_argument("--cells", action="store_true",
                    help="group run dirs by name (strip -repN) and report mean/min-max per cell")
    ap.add_argument("--scores", default="scores.csv", help="scores.csv or scores_relaxed.csv")
    a = ap.parse_args(argv)
    global SCORES_FILE
    SCORES_FILE = a.scores
    runs = [run_stats(Path(r)) for r in a.runs]
    data = {"filter": filter_stats(), "runs": runs, "scores_file": a.scores}
    if a.cells:
        import re as _re
        from eval.determinism import signature as _sig
        groups: dict = {}
        for r, path in zip(runs, a.runs):
            groups.setdefault(_re.sub(r"-rep\d+$", "", r["name"]), []).append((r, Path(path)))
        cells = []
        for name, members in groups.items():
            det = None
            if len(members) > 1:
                ids = [i for i in members[0][0]["item_ids"]]
                same = sum(1 for i in ids
                           if len({_sig(m[1] / "generated" / f"{safe_name(i)}.ids") for m in members}) == 1
                           and all((m[1] / "generated" / f"{safe_name(i)}.ids").exists() for m in members))
                det = {"identical": same, "items": len(ids)}
            cells.append(cell_stats([m[0] for m in members], name, det))
        data["cells"] = cells
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {a.out}: filter + {len(data['runs'])} runs")


if __name__ == "__main__":
    main()
