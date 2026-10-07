"""The determinacy labels that rest on a judgement call, and what the headline does without them
(v8 section 4).

    python -m eval.analysis_judgement

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

Of the 45 undetermined labels, 37 follow a stated rule: 14 drop a whole requirement the request
never mentions, and 23 drop a value list under the enumeration rule (the request names a property
but none of the values the reference enumerates). The remaining 8 are judgement calls about
patterns, fixed values and one numeric bound -- a reader could defend keeping them. This section
lists all 8 and reports the determined-only headline twice: once with them dropped (the published
variant) and once with them kept, so the reader can see how much rests on them.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks

OUT = EVAL_DIR / "reports" / "v8"
ANN = EVAL_DIR / "annotations" / "determinacy.jsonl"
GROUPS = {"Run 5 (2.5 Flash, 47 items x 3)": [f"run5-rep{r}" for r in (1, 2, 3)],
          "Run 6 (3.8 Flash, 47 items x 2)": ["run6-flash-rep1", "run6-flash-rep2"]}
B = 2000
RNG = np.random.default_rng(20261007)


def labels() -> pd.DataFrame:
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    rows = []
    for line in open(ANN, encoding="utf-8"):
        r = json.loads(line)
        if not (r["scope"] == "value" and r["method"] == "A-heuristic"):
            continue
        item = tasks[r["id"]]
        name = r["facet"].split(".")[-1].split()[-1]
        hits = [x for x in item["prompt"].get("requirements", []) if name.lower() in x.lower()]
        says = hits[0] if hits else "(the request never names this property)"
        rows.append({"item": r["id"], "spec": r["id"].split("#")[-1],
                     "facet": r["facet"], "reference value": r["value"],
                     "reason given": r["reason"],
                     "what the request says about it": " ".join(says.split())[:300]})
    return pd.DataFrame(rows)


def ci(frames: list[pd.DataFrame], col: str = "wit_outcome_equiv"):
    d = pd.concat(frames)
    d = d[d[col].notna()]
    per = {i: g[col].to_numpy(float) for i, g in d.groupby("id")}
    ids = sorted(per)
    n = len(ids)
    point = float(np.mean([v for i in ids for v in per[i]]))
    boots = [np.mean([v for j in RNG.integers(0, n, n) for v in per[ids[j]]]) for _ in range(B)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi), len(d), int(d[col].sum())


def headline() -> pd.DataFrame:
    rows = []
    for label, runs in GROUPS.items():
        for tag, treatment in (("", "the 8 treated as not derivable (published variant)"),
                               ("_j8", "the 8 treated as derivable (value constraints kept)")):
            for probe in (False, True):
                frames = []
                for run in runs:
                    f = RUNS_DIR / run / f"scores_relaxed{tag}{'_probe' if probe else ''}.csv"
                    d = pd.read_csv(f)
                    frames.append(d[d.ifc_only == 1])
                est, lo, hi, n, exact = ci(frames)
                rows.append({"group": label, "treatment": treatment,
                             "object set": "probe" if probe else "standard",
                             "item_runs": n, "exact": exact,
                             "S1 determined-only": round(est, 4),
                             "ci_low": round(lo, 4), "ci_high": round(hi, 4)})
    return pd.DataFrame(rows)


def affected() -> pd.DataFrame:
    """Which item-runs actually change verdict when the 8 labels are kept."""
    rows = []
    for label, runs in GROUPS.items():
        for probe in (False, True):
            for run in runs:
                a = pd.read_csv(RUNS_DIR / run / f"scores_relaxed{'_probe' if probe else ''}.csv")
                b = pd.read_csv(RUNS_DIR / run / f"scores_relaxed_j8{'_probe' if probe else ''}.csv")
                a, b = a[a.ifc_only == 1].set_index("id"), b[b.ifc_only == 1].set_index("id")
                for i in a.index:
                    if i not in b.index:
                        continue
                    x, y = a.loc[i, "wit_outcome_equiv"], b.loc[i, "wit_outcome_equiv"]
                    if pd.isna(x) or pd.isna(y) or x == y:
                        continue
                    rows.append({"group": label, "object set": "probe" if probe else "standard",
                                 "run": run, "id": i,
                                 "exact with the 8 dropped": int(x),
                                 "exact with the 8 kept": int(y)})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lb = labels()
    lb.to_csv(OUT / "j1_judgement_call_labels.csv", index=False)
    print(f"=== 4. the {len(lb)} determinacy labels that rest on a judgement call")
    print()
    for _, r in lb.iterrows():
        print(f"  item #{r.spec:<4} {r.facet}")
        print(f"      reference value: {r['reference value']}")
        print(f"      reason:          {r['reason given']}")
        print(f"      request text:    {r['what the request says about it'][:150]}")
    hl = headline()
    hl.to_csv(OUT / "j2_headline_both_ways.csv", index=False)
    print()
    print("=== the determined-only headline with those 8 labels either way")
    print()
    for _, r in hl.iterrows():
        print(f"  {r.group:<34}{r['object set']:<10}{r.treatment:<52}"
              f"{r['S1 determined-only']:>6.3f}  [{r.ci_low:.3f},{r.ci_high:.3f}]"
              f"  ({r.exact}/{r.item_runs})")
    af = affected()
    af.to_csv(OUT / "j3_affected_item_runs.csv", index=False)
    print()
    print(f"=== item-runs whose verdict depends on those 8 labels: {len(af)}")
    if len(af):
        print(af.groupby(["group", "object set"]).size().to_string())
    print()
    print(f"wrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
