"""Per-field fix effects, text-vs-behaviour pairs, and the v5 reconciliation (v8 §1b-§1d).

    python -m eval.analysis_fixes

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

§1b asks the key question directly: does the dataType fix move the dataType FIELD, and does the
lookup fix move the name fields? Effects are computed per item (all repeats of an item averaged
first) with 95% bootstrap intervals over items, exactly as in the v7 table.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval import score as S
from eval.analysis_values import matched_pairs, normalise_value
from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks, safe_name

OUT = EVAL_DIR / "reports" / "v8"
CELLS = ("lk0dt0", "lk1dt0", "lk0dt1", "lk1dt1")
REPEATS = (1, 2, 3)
B = 2000
RNG = np.random.default_rng(20261007)


# --------------------------------------------------------------------------- §1b
def per_item_fields(cell: str) -> pd.DataFrame:
    """Per item: name-match rate over reference requirements, and field agreement among matched."""
    runs = [f"run6-{cell}-rep{r}" for r in REPEATS]
    mp = matched_pairs(runs)
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    n_ref = {i: len(tasks[i]["target"]) for i in tasks}
    rows = []
    for iid, g in mp.groupby("id"):
        reps = g.run.nunique() or 1
        v = g[g.ref_has_value | g.gen_has_value]
        rows.append({
            "id": iid,
            "name_match_rate": len(g) / (n_ref[iid] * reps),
            "dataType_rate": g.dataType_agree.mean(),
            "cardinality_rate": g.cardinality_agree.mean(),
            "value_rate_norm": v.norm_agree.mean() if len(v) else np.nan,
            "value_omitted_rate": (g.ref_has_value & ~g.gen_has_value).mean(),
        })
    return pd.DataFrame(rows).set_index("id")


def field_effects() -> pd.DataFrame:
    per = {c: per_item_fields(c) for c in CELLS}
    fields = ["name_match_rate", "dataType_rate", "cardinality_rate", "value_rate_norm",
              "value_omitted_rate"]
    rows = []
    for f in fields:
        items = sorted(set.intersection(*[set(per[c][f].dropna().index) for c in CELLS]))
        M = {c: per[c].loc[items, f].to_numpy(dtype=float) for c in CELLS}
        n = len(items)

        def stat(idx):
            m = {c: M[c][idx].mean() for c in CELLS}
            lk = (m["lk1dt0"] + m["lk1dt1"]) / 2 - (m["lk0dt0"] + m["lk0dt1"]) / 2
            dt = (m["lk0dt1"] + m["lk1dt1"]) / 2 - (m["lk0dt0"] + m["lk1dt0"]) / 2
            return lk, dt, m

        point = stat(np.arange(n))
        boots = np.array([stat(RNG.integers(0, n, n))[:2] for _ in range(B)])
        for j, eff in enumerate(("lookup fix", "dataType fix")):
            lo, hi = np.percentile(boots[:, j], [2.5, 97.5])
            rows.append({"field": f, "effect": eff, "estimate": round(point[j], 4),
                         "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                         "excludes_zero": bool(lo > 0 or hi < 0), "n_items": n,
                         **{c: round(point[2][c], 4) for c in CELLS}})
    return pd.DataFrame(rows)


def worked_examples() -> pd.DataFrame:
    """One wrong type that rejects everything, one missing value list that is too lenient."""
    from eval.analysis_values import facet_xml
    rows = []
    # wrong type: dataType fix OFF, FireRating typed IFCTEXT where the reference wants IFCLABEL
    for cell, iid, pset, base in (("lk1dt0", "IDS4ALL-Template_Example specifications.ids#4",
                                   "Pset_WallCommon", "FireRating"),):
        run = f"run6-{cell}-rep1"
        rows.append({
            "example": "wrong data type rejects every conforming object",
            "run": run, "id": iid,
            "reference": facet_xml(RUNS_DIR / run / "reference" / f"{safe_name(iid)}.ids", pset, base, None),
            "generated": facet_xml(RUNS_DIR / run / "generated" / f"{safe_name(iid)}.ids", pset, base, None),
            "behaviour": "the checker reports 'data type \"IfcLabel\" does not match the required "
                         "IFCTEXT', so every wall the reference accepts is rejected (over-strict)"})
    # missing value list: a Status enumeration the generated file leaves unconstrained
    for run, iid, pset, base in (("run5-rep1",
                                  "Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#18",
                                  "Pset_SolarDeviceTypeCommon", "Status"),):
        rows.append({
            "example": "truncated value list rejects objects the reference accepts",
            "run": run, "id": iid,
            "reference": facet_xml(RUNS_DIR / run / "reference" / f"{safe_name(iid)}.ids", pset, base, None),
            "generated": facet_xml(RUNS_DIR / run / "generated" / f"{safe_name(iid)}.ids", pset, base, None),
            "behaviour": "the generated file allows 4 of the reference's 7 Status values (OTHER, "
                         "NOTKNOWN and UNSET are dropped), so a device with Status UNSET passes the "
                         "reference and fails the generated file (over-strict). No standard test "
                         "object uses those three values, so only the probe objects expose it"})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- §1c
def text_vs_behaviour(runs: list[str], label: str) -> pd.DataFrame:
    """Matched pairs: the text verdict and the behaviour verdict for the same item-run."""
    rows = []
    for relaxed in (False, True):
        suffix = "_relaxed" if relaxed else ""
        scoring = "determined-only" if relaxed else "strict"
        for run in runs:
            f = RUNS_DIR / run / f"scores{suffix}.csv"
            if not f.exists():
                continue
            d = pd.read_csv(f)
            d = d[(d.ifc_only == 1) & d.wit_outcome_equiv.notna()]
            for _, r in d.iterrows():
                rows.append({"group": label, "scoring": scoring, "run": run, "id": r.id,
                             "text_exact": int(r.facet_f1 == 1.0),
                             "names_correct": int(r.loose_f1 == 1.0),
                             "behaviour_exact": int(r.wit_outcome_equiv),
                             "s2": r.wit_s2})
    return pd.DataFrame(rows)


def contingency(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (group, scoring), g in df.groupby(["group", "scoring"]):
        for text_col in ("text_exact", "names_correct"):
            n11 = int(((g[text_col] == 1) & (g.behaviour_exact == 1)).sum())
            n10 = int(((g[text_col] == 1) & (g.behaviour_exact == 0)).sum())
            n01 = int(((g[text_col] == 0) & (g.behaviour_exact == 1)).sum())
            n00 = int(((g[text_col] == 0) & (g.behaviour_exact == 0)).sum())
            rows.append({"group": group, "scoring": scoring, "text measure": text_col,
                         "text ok & behaviour ok": n11, "text ok & behaviour wrong": n10,
                         "text wrong & behaviour ok": n01, "text wrong & behaviour wrong": n00,
                         "item_runs": n11 + n10 + n01 + n00,
                         "P(behaviour ok | text ok)": round(n11 / (n11 + n10), 3) if n11 + n10 else None,
                         "P(behaviour ok | text wrong)": round(n01 / (n01 + n00), 3) if n01 + n00 else None})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- §1d
def v5_reconciliation() -> pd.DataFrame:
    """Why the lookup fix looked like +0.10 facet F1 in v5 and +0.003 in v7."""
    rows = []
    for label, run in (("v5 run2-fixed (lookup on, 1 run)", "run2-fixed"),
                       ("v5 run3-no-trunc (lookup off, 1 run)", "run3-no-trunc")):
        d = pd.read_csv(RUNS_DIR / run / "scores.csv")
        d = d[d.ifc_only == 1]
        tp, fp, fn = d.facet_tp.sum(), d.facet_fp.sum(), d.facet_fn.sum()
        rows.append({"source": label, "items": len(d), "facet_f1_micro": round(S.prf(tp, fp, fn)[2], 4),
                     "facet_f1_macro": round(d.facet_f1.mean(), 4)})
    for cell in CELLS:
        vals_micro, vals_macro = [], []
        for r in REPEATS:
            d = pd.read_csv(RUNS_DIR / f"run6-{cell}-rep{r}" / "scores.csv")
            d = d[d.ifc_only == 1]
            tp, fp, fn = d.facet_tp.sum(), d.facet_fp.sum(), d.facet_fn.sum()
            vals_micro.append(S.prf(tp, fp, fn)[2])
            vals_macro.append(d.facet_f1.mean())
        rows.append({"source": f"v7 2x2 cell {cell} (3 repeats)", "items": len(d),
                     "facet_f1_micro": round(float(np.mean(vals_micro)), 4),
                     "facet_f1_macro": round(float(np.mean(vals_macro)), 4),
                     "micro_min": round(min(vals_micro), 4), "micro_max": round(max(vals_micro), 4)})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fe = field_effects()
    fe.to_csv(OUT / "f1_field_effects.csv", index=False)
    print("=== 1b. effect of each fix on each FIELD (95% bootstrap CI over items)")
    for _, r in fe.iterrows():
        star = " *" if r.excludes_zero else "  "
        print(f"  {r.field:<22}{r.effect:<14}{r.estimate:>8.3f}  [{r.ci_low:>7.3f},{r.ci_high:>7.3f}]{star}")

    we = worked_examples()
    we.to_csv(OUT / "f2_worked_examples.csv", index=False)
    print("\n=== 1b. worked examples")
    for _, r in we.iterrows():
        print(f"  {r.example}")
        print(f"    reference: {r.reference[:110]}")
        print(f"    generated: {r.generated[:110]}")
        print(f"    -> {r.behaviour}")

    tv = pd.concat([text_vs_behaviour([f"run5-rep{r}" for r in REPEATS], "Run 5 (2.5 Flash)"),
                    text_vs_behaviour(["run6-flash-rep1", "run6-flash-rep2"], "Run 6 (3.8 Flash)")])
    tv.to_csv(OUT / "f3_text_vs_behaviour_pairs.csv", index=False)
    ct = contingency(tv)
    ct.to_csv(OUT / "f4_text_vs_behaviour_contingency.csv", index=False)
    print("\n=== 1c. matched pairs: text verdict against behaviour verdict")
    print(ct.to_string(index=False))

    rec = v5_reconciliation()
    rec.to_csv(OUT / "f5_v5_reconciliation.csv", index=False)
    print("\n=== 1d. reconciling the v5 and v7 lookup-fix figures")
    print(rec.to_string(index=False))
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
