"""Like-for-like comparison of the text metric and the behaviour metric (v8 §2).

    python -m eval.analysis_likeforlike

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

The point of the table: the two fixes are judged by the same experiment, the same items and the
same repeats, so the effect on facet F1 and the effect on S1 can be put side by side. A fix that
moves one and not the other tells you which metric is blind to it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from eval.analysis import CELLS, REPEATS, item_matrix
from eval.common import EVAL_DIR

OUT = EVAL_DIR / "reports" / "v8"
B = 2000
RNG = np.random.default_rng(20261007)

# (column, scores file, label) -- the pairs are deliberately matched: same column family,
# same scoring variant, so each text row has a behaviour row directly beneath it.
ROWS = [
    ("facet_f1", "strict", "facet F1, strict (text)"),
    ("wit_outcome_equiv", "strict", "S1, strict (behaviour)"),
    ("facet_f1", "relaxed", "facet F1, determined-only (text)"),
    ("wit_outcome_equiv", "relaxed", "S1, determined-only (behaviour)"),
    ("names_correct", "strict", "names-correct rate, strict (text)"),
    ("wit_s2_ref", "strict", "S2 on reference objects, strict (behaviour)"),
]


def table() -> pd.DataFrame:
    rows = []
    for col, which, label in ROWS:
        per_cell = {c: item_matrix(c, col, which) for c in CELLS}
        items = sorted(set.intersection(*[set(s.dropna().index) for s in per_cell.values()]))
        M = {c: per_cell[c].loc[items].to_numpy(dtype=float) for c in CELLS}
        n = len(items)

        def stat(idx):
            m = {c: M[c][idx].mean() for c in CELLS}
            lookup = (m["lk1dt0"] + m["lk1dt1"]) / 2 - (m["lk0dt0"] + m["lk0dt1"]) / 2
            dtype = (m["lk0dt1"] + m["lk1dt1"]) / 2 - (m["lk0dt0"] + m["lk1dt0"]) / 2
            return lookup, dtype, m

        point = stat(np.arange(n))
        boots = np.array([stat(RNG.integers(0, n, n))[:2] for _ in range(B)])
        for j, eff in enumerate(("lookup fix", "dataType fix")):
            lo, hi = np.percentile(boots[:, j], [2.5, 97.5])
            rows.append({"measure": label, "effect": eff, "estimate": round(point[j], 4),
                         "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                         "excludes_zero": bool(lo > 0 or hi < 0), "n_items": n,
                         "repeats_per_cell": len(REPEATS),
                         **{f"cell_{c}": round(point[2][c], 4) for c in CELLS}})
    return pd.DataFrame(rows)


def field_rows() -> pd.DataFrame:
    """The per-field effects from §1b, so the field-level and item-level numbers sit together."""
    f = OUT / "f1_field_effects.csv"
    if not f.exists():
        return pd.DataFrame()
    d = pd.read_csv(f)
    keep = {"dataType_rate": "dataType field, among name-matched requirements",
            "name_match_rate": "name-match rate over reference requirements",
            "value_rate_norm": "value field (normalised), among name-matched requirements"}
    d = d[d.field.isin(keep)].copy()
    d["measure"] = d.field.map(keep)
    d["effect"] = d.effect.str.replace("fix", "fix", regex=False)
    return d[["measure", "effect", "estimate", "ci_low", "ci_high", "excludes_zero", "n_items"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = table()
    t.to_csv(OUT / "l1_like_for_like_effects.csv", index=False)
    print("=== 2. the same experiment judged by the text metric and by behaviour")
    print("    (2x2 cells, 21 items x 3 repeats; 95% bootstrap CI over items)\n")
    for eff in ("lookup fix", "dataType fix"):
        print(f"  {eff}")
        for _, r in t[t.effect == eff].iterrows():
            star = " *" if r.excludes_zero else "  "
            print(f"    {r.measure:<46}{r.estimate:>+8.3f}  [{r.ci_low:>+7.3f},{r.ci_high:>+7.3f}]{star}")
        print()

    fr = field_rows()
    if len(fr):
        fr.to_csv(OUT / "l2_field_effects_for_comparison.csv", index=False)
        print("  for comparison, the same fixes measured on the FIELD that each one targets:")
        for _, r in fr.iterrows():
            star = " *" if r.excludes_zero else "  "
            print(f"    {r.effect:<14}{r.measure:<56}{r.estimate:>+8.3f}"
                  f"  [{r.ci_low:>+7.3f},{r.ci_high:>+7.3f}]{star}")
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
