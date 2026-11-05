"""S1 under the standard object set and under the probe object set (v8 §1 of the addendum).

    python -m eval.analysis_probe

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

A test object only discriminates two files if some requirement actually treats it differently.
Where the reference allows {A,B,C} and the generated file allows {A,B,D}, objects built from the
reference alone never use D and objects built from the candidate alone never use C, so every
object can agree and the difference goes unmeasured. The probe variant adds one object per value
in the SYMMETRIC DIFFERENCE of the two value lists, each accepted by exactly one of the files.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from eval.common import EVAL_DIR, RUNS_DIR

OUT = EVAL_DIR / "reports" / "v8"
GROUPS = {"Run 5 (2.5 Flash, 47 items x 3)": [f"run5-rep{r}" for r in (1, 2, 3)],
          "Run 6 (3.8 Flash, 47 items x 2)": ["run6-flash-rep1", "run6-flash-rep2"],
          "Run 7 (Claude Sonnet 5.5 via Claude Code, 47 items x 3)": [f"run7-claude-rep{r}" for r in (1, 2, 3)],
          # handover 2: the same Run 7 files under the v9b scorer (cardinality annotation), then Run 8
          "Run 7 rescored (Sonnet 5.5, v9b scorer, 47 items x 3)": [f"run7-claude-rep{r}-rescored-v9b" for r in (1, 2, 3)],
          "Run 8 (Sonnet 5.5, dev fixes, 47 items x 1)": ["run8-claude-rep1"],
          "Run 8 (Opus 5.5, dev fixes, 47 items x 1)": ["run8-opus-rep1"],
          "Run 10 (Sonnet 5.5, + applicability facets, 47 items x 1)": ["run10-claude-rep1"]}
B = 2000
RNG = np.random.default_rng(20261007)


def read(run: str, relaxed: bool, probe: bool) -> pd.DataFrame:
    f = RUNS_DIR / run / f"scores{'_relaxed' if relaxed else ''}{'_probe' if probe else ''}.csv"
    d = pd.read_csv(f)
    return d[d.ifc_only == 1].copy()


def rate_ci(frames: list[pd.DataFrame], col: str) -> tuple[float, float, float, int, int]:
    """Mean of `col` with a bootstrap CI that resamples ITEMS and carries their repeats."""
    d = pd.concat(frames)
    d = d[d[col].notna()]
    per_item = {i: g[col].to_numpy(dtype=float) for i, g in d.groupby("id")}
    ids = sorted(per_item)
    n = len(ids)
    point = float(np.mean([v for i in ids for v in per_item[i]]))
    boots = []
    for _ in range(B):
        pick = RNG.integers(0, n, n)
        vals = [v for j in pick for v in per_item[ids[j]]]
        boots.append(np.mean(vals))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi), len(d), n


def table() -> pd.DataFrame:
    rows = []
    for label, runs in GROUPS.items():
        for relaxed in (False, True):
            scoring = "determined-only" if relaxed else "strict"
            for probe in (False, True):
                frames = [read(r, relaxed, probe) for r in runs]
                est, lo, hi, n_runs, n_items = rate_ci(frames, "wit_outcome_equiv")
                s2, s2lo, s2hi, _, _ = rate_ci(frames, "wit_s2_ref")
                probe_objs = 0
                for f in frames:
                    for s in f.wit_sides.dropna():
                        try:
                            probe_objs += int(eval(s).get("probe", 0))
                        except Exception:
                            pass
                rows.append({"group": label, "scoring": scoring,
                             "object set": "probe" if probe else "standard",
                             "item_runs": n_runs, "items": n_items,
                             "S1": round(est, 4), "S1_ci_low": round(lo, 4), "S1_ci_high": round(hi, 4),
                             "S1_exact_count": int(round(est * n_runs)),
                             "S2_ref": round(s2, 4), "S2_ci_low": round(s2lo, 4),
                             "S2_ci_high": round(s2hi, 4),
                             "probe_objects_total": probe_objs})
    return pd.DataFrame(rows)


def flips() -> pd.DataFrame:
    """Item-runs that the standard object set calls behaviour-exact and the probe set does not."""
    rows = []
    for label, runs in GROUPS.items():
        for relaxed in (False, True):
            scoring = "determined-only" if relaxed else "strict"
            for run in runs:
                a = read(run, relaxed, False).set_index("id")
                b = read(run, relaxed, True).set_index("id")
                common = [i for i in a.index if i in b.index]
                for i in common:
                    x, y = a.loc[i, "wit_outcome_equiv"], b.loc[i, "wit_outcome_equiv"]
                    if pd.isna(x) or pd.isna(y) or x == y:
                        continue
                    sides = b.loc[i, "wit_sides"]
                    rows.append({"group": label, "scoring": scoring, "run": run, "id": i,
                                 "standard": int(x), "probe": int(y),
                                 "direction_probe": b.loc[i, "wit_direction"],
                                 "probe_objects": sides})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = table()
    t.to_csv(OUT / "p1_probe_vs_standard.csv", index=False)
    print("=== S1 under the two object sets (95% bootstrap CI over items)\n")
    for label in GROUPS:
        print(f"  {label}")
        for _, r in t[t.group == label].iterrows():
            print(f"    {r.scoring:<16}{r['object set']:<10}"
                  f"S1 {r.S1:>6.3f}  [{r.S1_ci_low:.3f},{r.S1_ci_high:.3f}]"
                  f"  ({r.S1_exact_count}/{r.item_runs} item-runs)"
                  f"   S2 {r.S2_ref:>6.3f}   probe objects {r.probe_objects_total}")
        print()
    fl = flips()
    fl.to_csv(OUT / "p2_probe_flips.csv", index=False)
    print(f"=== item-runs whose verdict changes when the probe objects are added: {len(fl)}")
    if len(fl):
        print(fl.groupby(["group", "scoring"]).size().to_string())
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
