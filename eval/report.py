"""Print the v5 study summary for one or more scored runs.

    python -m eval.report <run_dir> [<run_dir> ...]

Every scored item counts. Metrics (see eval/score.py):
  S1  strict  — identical verdict on every test object (the v4 headline)
  S2  graded  — fraction of test objects both specifications judge the same way
  S3  decomposed — requirement enforcement, false rejection, applicability
Test models are synthetic and built from BOTH specifications; they measure agreement on
each requirement's own boundary cases, not on realistic building data.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from eval.common import RUNS_DIR, SPEC_TASKS, graph_psets, ifc_only, load_tasks
from eval.score import ERROR_COLS, FACET_KINDS, prf

MIN_DISTINCT_F1 = 10
BANDS = ["<=3", "4-9", ">=10"]
GUARD_ORDER = ["value_coerced_from_string", "value_coerced_from_alias", "requirements_coerced_from_list",
               "value_looks_like_pattern", "value_looks_like_description", "value_is_placeholder",
               "empty_restriction_rejected"]


def pct(x, n):
    return f"{x}/{n} = {100 * x / n:.0f}%" if n else "n/a"


def num(x, dp=3):
    return "n/a" if x is None or (isinstance(x, float) and pd.isna(x)) else f"{x:.{dp}f}"


def hr(t):
    print(f"\n{'=' * 84}\n{t}\n{'=' * 84}")


def load(run: Path) -> dict:
    df = pd.read_csv(run / "scores.csv")
    if "ifc_only" in df:
        df = df[df.ifc_only == 1].copy()
    logs = {}
    log_path = run / "log.jsonl"
    if not log_path.exists() and (run / "score_meta.json").exists():   # scored with --out
        log_path = Path(json.loads((run / "score_meta.json").read_text())["source_run"]) / "log.jsonl"
    keep_ids = set(df.id)
    if log_path.exists():
        for line in open(log_path, encoding="utf-8"):
            r = json.loads(line)
            if r["id"] in keep_ids:                  # only the items this report counts
                logs[r["id"]] = r
    meta_path = run / "run.json" if (run / "run.json").exists() else log_path.parent / "run.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {"name": run.name, "df": df, "logs": logs, "meta": meta}


# --------------------------------------------------------------------------- blocks
def block_filter():
    hr("1. THE FILTER — which items the study can use")
    tasks = load_tasks(SPEC_TASKS)
    psets = graph_psets(RUNS_DIR / "spec_gemini-2.5-flash")
    if psets is None:
        print("  graph unavailable; cannot recompute the filter")
        return
    keep = [t for t in tasks if ifc_only(t, psets)]
    print(f"  published specifications harvested: {len(tasks)}")
    print(f"  usable (every required property is a standard IFC property in the graph): {len(keep)}")
    print(f"  excluded (project-specific property sets such as WienBV_* / ePset_OMA_*): {len(tasks) - len(keep)}")
    src = Counter(t["source"] for t in keep)
    for s, n in src.most_common():
        print(f"    {n:>3}  {s[:64]}")
    print(f"  requirement-count bands among the usable items: " +
          ", ".join(f"{b}: {sum(1 for t in keep if band_of(len(t['target'])) == b)}" for b in BANDS))


def band_of(n: int) -> str:
    return "<=3" if n <= 3 else ("4-9" if n <= 9 else ">=10")


def block_pipeline(runs: list[dict]):
    hr("2. PIPELINE HEALTH — how often each guard fired (0 for the fixed guards means clean)")
    print(f"  {'run':<22}{'items':>6}{'no_file':>8}{'gen_att':>8}{'psets_dropped':>15}{'max_tool_chars':>15}")
    for r in runs:
        logs = r["logs"].values()
        if not logs:
            print(f"  {r['name']:<22}{'(no log)':>6}")
            continue
        nf = sum(1 for x in logs if x["status"] != "ok")
        att = [x.get("retries", {}).get("generate_ids_attempts", 0) for x in logs]
        has_trunc_log = any("property_sets_dropped" in x for x in logs)
        dropped = (str(sum(len(x.get("property_sets_dropped") or []) for x in logs))
                   if has_trunc_log else "not logged")
        mx = (f"{max((x.get('tool_result_chars_max') or 0) for x in logs):,}"
              if has_trunc_log else "not logged")
        print(f"  {r['name']:<22}{len(list(logs)):>6}{nf:>8}{sum(att) / max(len(att), 1):>8.1f}{dropped:>15}{mx:>15}")
    print()
    print(f"  {'guard':<32}" + "".join(f"{r['name'][:14]:>16}" for r in runs))
    guards = {r["name"]: Counter() for r in runs}
    for r in runs:
        for x in r["logs"].values():
            guards[r["name"]].update(x.get("guards_fired") or {})
    keys = GUARD_ORDER + sorted({k for g in guards.values() for k in g} - set(GUARD_ORDER))
    for k in keys:
        if any(guards[r["name"]].get(k) for r in runs):
            print(f"  {k:<32}" + "".join(f"{guards[r['name']].get(k, 0):>16}" for r in runs))
    print("  (v4 predates this logging, hence 'not logged'; it dropped sets — measured separately)")
    print("  (coerced_* = an unambiguous shape accepted and logged; *_rejected / looks_like_* = returned to\n"
          "   the model as an error to retry; psets_dropped must be 0 — a dropped set is an invented name)")


def metrics(df: pd.DataFrame) -> dict:
    ok = df[df.status == "ok"]
    ext = df[df.wit_outcome_equiv.notna()] if "wit_outcome_equiv" in df else df.iloc[0:0]
    g = lambda c: ext[c].dropna() if c in ext else pd.Series(dtype=float)
    tp, fp, fn = df.facet_tp.sum(), df.facet_fp.sum(), df.facet_fn.sum()
    return {
        "items": len(df), "with_file": len(ok), "testable": len(ext),
        "S1": (int(ext.wit_outcome_equiv.sum()), len(ext)),
        "S2": g("wit_s2").mean() if len(g("wit_s2")) else None,
        "S2_ref": g("wit_s2_ref").mean() if len(g("wit_s2_ref")) else None,
        "S2_cand": g("wit_s2_cand").mean() if len(g("wit_s2_cand")) else None,
        "enforce": g("wit_enforce").mean() if len(g("wit_enforce")) else None,
        "false_reject": g("wit_false_reject").mean() if len(g("wit_false_reject")) else None,
        "app_out": g("wit_app_out").mean() if len(g("wit_app_out")) else None,
        "app_in": g("wit_app_in").mean() if len(g("wit_app_in")) else None,
        "facet_f1_micro": prf(tp, fp, fn)[2], "facet_f1_macro": df.facet_f1.mean(),
        "names_correct": (int(df.names_correct.sum()) if "names_correct" in df
                          else int((df.loose_f1 == 1.0).sum()), len(df)),
    }


def block_main(runs: list[dict]):
    hr("3. MAIN RESULTS")
    rows = [("items scored", lambda m: str(m["items"])),
            ("produced a file", lambda m: pct(m["with_file"], m["items"])),
            ("testable (verified test model)", lambda m: pct(m["testable"], m["items"])),
            ("S1 strict: identical verdicts", lambda m: pct(*m["S1"])),
            ("S2 object agreement (mean)", lambda m: num(m["S2"])),
            ("   S2 on reference-derived objects", lambda m: num(m["S2_ref"])),
            ("   S2 on candidate-derived objects", lambda m: num(m["S2_cand"])),
            ("S3 requirement enforcement", lambda m: num(m["enforce"])),
            ("S3 false rejection (lower better)", lambda m: num(m["false_reject"])),
            ("S3 applicability: ignores out-of-scope", lambda m: num(m["app_out"])),
            ("S3 applicability: covers in-scope", lambda m: num(m["app_in"])),
            ("facet F1 (micro)", lambda m: num(m["facet_f1_micro"])),
            ("facet F1 (macro)", lambda m: num(m["facet_f1_macro"])),
            ("names-correct items", lambda m: pct(*m["names_correct"])),
            ]
    ms = {r["name"]: metrics(r["df"]) for r in runs}
    print(f"  {'metric':<38}" + "".join(f"{r['name'][:16]:>18}" for r in runs))
    for label, fn in rows:
        print(f"  {label:<38}" + "".join(f"{fn(ms[r['name']]):>18}" for r in runs))


def block_bands(runs: list[dict]):
    hr("4. BY SPEC LENGTH — strict scoring punishes long specs; graded scoring should not")
    for r in runs:
        df = r["df"]
        if "band" not in df:
            continue
        print(f"  {r['name']}")
        print(f"    {'band':<8}{'items':>6}{'S1':>12}{'S2':>8}{'enforce':>9}{'false_rej':>10}{'facetF1':>9}")
        for b in BANDS:
            sub = df[df.band == b]
            ext = sub[sub.wit_outcome_equiv.notna()]
            if not len(sub):
                continue
            print(f"    {b:<8}{len(sub):>6}{pct(int(ext.wit_outcome_equiv.sum()), len(ext)):>12}"
                  f"{num(ext.wit_s2.mean(), 2):>8}{num(ext.wit_enforce.mean(), 2):>9}"
                  f"{num(ext.wit_false_reject.mean(), 2):>10}{num(sub.facet_f1.mean(), 2):>9}")


def block_hypothesis(runs: list[dict]):
    hr("5. NAMES-CORRECT vs BEHAVIOUR — the study's main hypothesis")
    print("  A name-level text check counts an item right when every property-set and property name")
    print("  matches. Does that item also behave like the reference?")
    for r in runs:
        df = r["df"]
        if "wit_outcome_equiv" not in df:
            continue
        ext = df[df.wit_outcome_equiv.notna()]
        nc = ext[ext.loose_f1 == 1.0]
        other = ext[ext.loose_f1 < 1.0]
        print(f"\n  {r['name']}")
        print(f"    names-correct items with a usable test model: {len(nc)}")
        print(f"      of those, S1-equivalent: {pct(int(nc.wit_outcome_equiv.sum()), len(nc))}"
              f"   mean S2 {num(nc.wit_s2.mean(), 3)}   mean enforcement {num(nc.wit_enforce.mean(), 3)}")
        print(f"    items with at least one wrong name: {len(other)}"
              f"   S1-equivalent {pct(int(other.wit_outcome_equiv.sum()), len(other))}"
              f"   mean S2 {num(other.wit_s2.mean(), 3)}")
        for _, row in nc.iterrows():
            if not row.wit_outcome_equiv:
                print(f"      divergent though names right: {row.id[-34:]}  S2={num(row.wit_s2, 2)}  "
                      f"{str(row.get('wit_direction'))}  [{str(row.get('wit_diverging'))[:60]}]")
        vals = ext.facet_f1.round(4)
        print(f"    distinct facet-F1 values: {vals.nunique()} -> {sorted(vals.unique().tolist())[:12]}")
        if vals.nunique() < MIN_DISTINCT_F1:
            print(f"    correlation NOT reported: fewer than {MIN_DISTINCT_F1} distinct facet-F1 values")
        else:
            print(f"    Spearman rho(facet-F1, S2) = {ext.facet_f1.corr(ext.wit_s2, method='spearman'):.3f}")


def block_errors(runs: list[dict]):
    hr("6. FAILURE MECHANISMS")
    pipeline_cols = ["err_empty_restriction", "err_placeholder_value", "err_no_file"]
    print("  pipeline-caused (should be 0 after the fixes; no_file may remain for other reasons)")
    print(f"    {'mechanism':<28}" + "".join(f"{r['name'][:14]:>16}" for r in runs))
    for c in pipeline_cols:
        if any(c in r["df"] for r in runs):
            print(f"    {c[4:]:<28}" + "".join(f"{int(r['df'][c].sum()) if c in r['df'] else 0:>16}" for r in runs))
    print("  model errors (what the study wants to measure)")
    for c in ERROR_COLS:
        col = f"err_{c}"
        if col in pipeline_cols or not any(col in r["df"] for r in runs):
            continue
        if any(int(r["df"][col].sum()) if col in r["df"] else 0 for r in runs):
            print(f"    {c:<28}" + "".join(f"{int(r['df'][col].sum()) if col in r['df'] else 0:>16}" for r in runs))


def block_cost(runs: list[dict]):
    hr("7. COST AND LATENCY")
    print(f"  {'run':<22}{'items':>6}{'s/item':>9}{'$/item':>9}{'$ total':>9}{'tools':>7}{'in_tok':>10}")
    for r in runs:
        logs = list(r["logs"].values())
        if not logs:
            continue
        n = len(logs)
        s = sum(x["wall_ms"] for x in logs) / n / 1000
        c = sum(x["cost_usd"] for x in logs) / n
        print(f"  {r['name']:<22}{n:>6}{s:>9.1f}{c:>9.4f}{c * n:>9.2f}"
              f"{sum(len(x['tool_calls']) for x in logs) / n:>7.1f}"
              f"{sum(x['input_tokens'] for x in logs) / n:>10,.0f}")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    runs = [load(Path(a)) for a in argv]
    for r in runs:
        fx = r["meta"].get("fixes")
        print(f"run {r['name']:<24} {('fixes: ' + json.dumps(fx)) if fx else 'v4 baseline (no fixes)'}")
    block_filter()
    block_pipeline(runs)
    block_main(runs)
    block_bands(runs)
    block_hypothesis(runs)
    block_errors(runs)
    block_cost(runs)


if __name__ == "__main__":
    main()
