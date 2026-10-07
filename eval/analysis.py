"""Analysis pass for report v7 (work order v7 §1-§4). Writes CSVs under eval/reports/v7/.

    python -m eval.analysis

Everything here is read-only over existing run directories. Uncertainty comes from a
bootstrap that resamples ITEMS with replacement, carrying all repeats of an item together,
because repeats are nested within items and are not independent observations.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks

OUT = EVAL_DIR / "reports" / "v7"
CELLS = {"lk0dt0": (0, 0), "lk1dt0": (1, 0), "lk0dt1": (0, 1), "lk1dt1": (1, 1)}
REPEATS = (1, 2, 3)
B = 2000
RNG = np.random.default_rng(20260925)

# per-item metrics: (column, higher_is_better, which scores file)
METRICS = [
    ("facet_f1", "text", "strict"),
    ("names_correct", "text", "strict"),
    ("wit_outcome_equiv", "behaviour", "strict"),        # S1 strict
    ("wit_outcome_equiv", "behaviour", "relaxed"),       # S1 determined-only
    ("wit_s2_ref", "behaviour", "strict"),
    ("wit_false_reject", "behaviour", "strict"),
]
LABEL = {("facet_f1", "strict"): "facet F1 (text)",
         ("names_correct", "strict"): "names-correct rate (text)",
         ("wit_outcome_equiv", "strict"): "S1 strict (behaviour)",
         ("wit_outcome_equiv", "relaxed"): "S1 determined-only (behaviour)",
         ("wit_s2_ref", "strict"): "S2 reference objects (behaviour)",
         ("wit_false_reject", "strict"): "false rejection (behaviour, lower better)"}


def read(run: str, which: str) -> pd.DataFrame:
    f = RUNS_DIR / run / ("scores.csv" if which == "strict" else "scores_relaxed.csv")
    d = pd.read_csv(f)
    return d[d.ifc_only == 1].copy() if "ifc_only" in d else d


def item_matrix(cell: str, col: str, which: str) -> pd.Series:
    """Mean of `col` per item across the three repeats of one 2x2 cell."""
    frames = [read(f"run6-{cell}-rep{r}", which).set_index("id")[col] for r in REPEATS]
    return pd.concat(frames, axis=1).mean(axis=1, skipna=True)


def effects_table() -> pd.DataFrame:
    rows = []
    for col, kind, which in METRICS:
        per_cell = {c: item_matrix(c, col, which) for c in CELLS}
        items = sorted(set.intersection(*[set(s.dropna().index) for s in per_cell.values()]))
        M = {c: per_cell[c].loc[items].to_numpy(dtype=float) for c in CELLS}
        n = len(items)

        def stat(idx):
            m = {c: M[c][idx].mean() for c in CELLS}
            lookup = (m["lk1dt0"] + m["lk1dt1"]) / 2 - (m["lk0dt0"] + m["lk0dt1"]) / 2
            dtype = (m["lk0dt1"] + m["lk1dt1"]) / 2 - (m["lk0dt0"] + m["lk1dt0"]) / 2
            inter = (m["lk1dt1"] - m["lk0dt1"]) - (m["lk1dt0"] - m["lk0dt0"])
            return lookup, dtype, inter, m

        point = stat(np.arange(n))
        boots = np.array([stat(RNG.integers(0, n, n))[:3] for _ in range(B)])
        for j, eff in enumerate(("lookup fix", "dataType fix", "interaction")):
            lo, hi = np.percentile(boots[:, j], [2.5, 97.5])
            rows.append({"metric": LABEL[(col, which)], "kind": kind, "effect": eff,
                         "estimate": round(point[j], 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                         "excludes_zero": bool(lo > 0 or hi < 0), "n_items": n,
                         **{f"cell_{c}": round(point[3][c], 4) for c in CELLS}})
    return pd.DataFrame(rows)


def within_item_table() -> tuple[pd.DataFrame, pd.DataFrame]:
    """P2 vs P3: with dataType on, what happened to items whose names the lookup fix fixed?"""
    before, after = "lk0dt1", "lk1dt1"
    nm_b, nm_a = item_matrix(before, "names_correct", "strict"), item_matrix(after, "names_correct", "strict")
    rows = []
    for col, which in (("wit_outcome_equiv", "strict"), ("wit_outcome_equiv", "relaxed"),
                       ("wit_s2_ref", "strict"), ("wit_false_reject", "strict")):
        b, a = item_matrix(before, col, which), item_matrix(after, col, which)
        for group, sel in (("names fixed by the lookup fix", (nm_b < 0.5) & (nm_a > 0.5)),
                           ("names already correct", (nm_b > 0.5) & (nm_a > 0.5)),
                           ("names wrong in both", (nm_b < 0.5) & (nm_a < 0.5)),
                           ("names broken by the lookup fix", (nm_b > 0.5) & (nm_a < 0.5))):
            idx = [i for i in sel[sel].index if i in b.index and i in a.index]
            vals_b, vals_a = b.loc[idx].dropna(), a.loc[idx].dropna()
            rows.append({"group": group, "metric": LABEL[(col, which)], "items": len(idx),
                         "before_lookup_off": round(vals_b.mean(), 3) if len(vals_b) else None,
                         "after_lookup_on": round(vals_a.mean(), 3) if len(vals_a) else None,
                         "change": (round(vals_a.mean() - vals_b.mean(), 3)
                                    if len(vals_b) and len(vals_a) else None)})
    # difficulty of names-correct vs names-wrong items (all-fixes cell)
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    ann: dict = {}
    for line in open(EVAL_DIR / "annotations" / "determinacy.jsonl", encoding="utf-8"):
        r = json.loads(line)
        ann.setdefault(r["id"], []).append(r)
    nm = item_matrix("lk1dt1", "names_correct", "strict")
    diff = []
    for group, sel in (("names-correct", nm > 0.5), ("names-wrong", nm < 0.5)):
        ids = list(sel[sel].index)
        tgt = [tasks[i]["target"] for i in ids]
        n_req = [len(t) for t in tgt]
        undet = [len(ann.get(i, [])) / max(len(tasks[i]["target"]), 1) for i in ids]
        kinds: dict = {}
        for t in tgt:
            for f in t:
                kinds[f["facet"]] = kinds.get(f["facet"], 0) + 1
        tot = sum(kinds.values()) or 1
        diff.append({"group": group, "items": len(ids),
                     "mean_requirements": round(float(np.mean(n_req)), 2) if ids else None,
                     "max_requirements": max(n_req) if ids else None,
                     "share_undetermined_facets": round(float(np.mean(undet)), 3) if ids else None,
                     **{f"facets_{k}": round(v / tot, 3) for k, v in sorted(kinds.items())}})
    return pd.DataFrame(rows), pd.DataFrame(diff)


def sensitivity_table() -> pd.DataFrame:
    """Run 5 headline under each annotation variant, plus the per-repeat breakdown."""
    variants = [("strict (no annotations)", "scores.csv"),
                ("pass B (final)", "scores_relaxed.csv"),
                ("pass A (script)", "scores_relaxed_passA.csv"),
                ("values kept, only unmentioned dropped", "scores_relaxed_valueskept.csv")]
    rows = []
    for label, fname in variants:
        per_item: dict = {}
        testable = exact = 0
        for r in REPEATS:
            f = RUNS_DIR / f"run5-rep{r}" / fname
            if not f.exists():
                break
            d = pd.read_csv(f)
            d = d[d.ifc_only == 1]
            e = d[d.wit_outcome_equiv.notna()]
            testable += len(e)
            exact += int(e.wit_outcome_equiv.sum())
            for _, row in e.iterrows():
                per_item.setdefault(row.id, []).append(int(row.wit_outcome_equiv))
        else:
            hits = {k: sum(v) for k, v in per_item.items()}
            rows.append({"variant": label, "scores_file": fname,
                         "items_testable_per_repeat": round(testable / len(REPEATS), 1),
                         "exact_per_repeat": round(exact / len(REPEATS), 1),
                         "exact_rate": round(exact / testable, 3) if testable else None,
                         "items_3of3": sum(1 for v in hits.values() if v == 3),
                         "items_2of3": sum(1 for v in hits.values() if v == 2),
                         "items_1of3": sum(1 for v in hits.values() if v == 1),
                         "items_0of3": sum(1 for v in hits.values() if v == 0)})
    return pd.DataFrame(rows)


def failures_table() -> pd.DataFrame:
    """Items that still fail under the determined-only reference, with the cause."""
    causes = [("wrong_value", "wrong value or allowed list"), ("wrong_datatype", "wrong data type"),
              ("missing_requirement", "missing requirement"), ("extra_requirement", "extra requirement"),
              ("hallucinated_pset", "invented property set"), ("wrong_pset", "wrong property set"),
              ("wrong_cardinality", "wrong cardinality"),
              ("ifcversion_excludes_model", "version mismatch"), ("no_file", "no file produced")]
    rows = []
    for r in REPEATS:
        d = pd.read_csv(RUNS_DIR / f"run5-rep{r}" / "scores_relaxed.csv")
        d = d[d.ifc_only == 1]
        e = d[d.wit_outcome_equiv.notna()]
        for _, row in e[e.wit_outcome_equiv == 0].iterrows():
            present = [lab for col, lab in causes if row.get(f"err_{col}", 0)]
            app = ("applicability: " + str(row.wit_direction)) if isinstance(row.wit_direction, str) and \
                "applicab" in str(row.wit_direction) else None
            rows.append({"repeat": r, "id": row.id, "requirements": row.n_target,
                         "s2": round(row.wit_s2, 3) if pd.notna(row.wit_s2) else None,
                         "direction": row.wit_direction,
                         "primary_cause": (present[0] if present else (app or "other")),
                         "all_causes": "; ".join(present) or (app or "other"),
                         "diverging_variants": str(row.get("wit_diverging"))[:120]})
    df = pd.DataFrame(rows)
    return df.sort_values(["repeat", "primary_cause", "id"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    eff = effects_table()
    eff.to_csv(OUT / "t1_fix_effects_bootstrap.csv", index=False)
    print("\n=== 1. EFFECT OF EACH FIX (95% bootstrap CI over items, repeats nested)")
    for _, r in eff.iterrows():
        star = "  *" if r.excludes_zero else "   "
        print(f"  {r.metric:<42}{r.effect:<14}{r.estimate:>8.3f}  [{r.ci_low:>7.3f},{r.ci_high:>7.3f}]{star}")

    wi, diff = within_item_table()
    wi.to_csv(OUT / "t2_within_item_lookup.csv", index=False)
    diff.to_csv(OUT / "t3_item_difficulty.csv", index=False)
    print("\n=== 2. WITHIN-ITEM: what the lookup fix did to items whose names it corrected")
    for _, r in wi[wi["items"] > 0].iterrows():
        print(f"  {r.group:<34}{r.metric:<42}n={r['items']:<3} {r.before_lookup_off} -> {r.after_lookup_on}")
    print("  item difficulty:")
    for _, r in diff.iterrows():
        print(f"    {r.group:<14}n={r['items']:<3} mean reqs {r.mean_requirements:<5} "
              f"max {r.max_requirements:<3} undetermined share {r.share_undetermined_facets}")

    sens = sensitivity_table()
    sens.to_csv(OUT / "t4_run5_sensitivity.csv", index=False)
    print("\n=== 3. RUN 5 HEADLINE SENSITIVITY")
    print(sens.to_string(index=False))

    fail = failures_table()
    fail.to_csv(OUT / "t5_run5_failures.csv", index=False)
    print("\n=== 4. WHAT STILL FAILS (determined-only, Run 5)")
    print(fail.primary_cause.value_counts().to_string())
    print(f"  distinct items failing in at least one repeat: {fail.id.nunique()}")
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
