"""Run 6 against Run 5: paired by item, the 3.8-Flash budget failures counted both ways,
value omission split by determinacy, and cost per item (v8 section 5).

    python -m eval.analysis_models

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

Run 5 is 2.5 Flash, 47 items x 3 repeats. Run 6 is 3.8 Flash, 47 items x 2 repeats, except
that repeat 2 stopped at 39 items when the prepaid credit ran out. Every comparison below is
restricted to items both runs attempted, and each item contributes the mean of its own repeats
before the two runs are differenced, so the unequal repeat counts cannot tilt the result.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from eval.analysis_values import matched_pairs
from eval.common import EVAL_DIR, RUNS_DIR

OUT = EVAL_DIR / "reports" / "v8"
RUN5 = [f"run5-rep{r}" for r in (1, 2, 3)]
RUN6 = ["run6-flash-rep1", "run6-flash-rep2"]
B = 2000
RNG = np.random.default_rng(20261007)

# (column, (scores-file suffix, probe), label)
METRICS = [
    ("facet_f1", ("", False), "facet F1 (text)"),
    ("names_correct", ("", False), "names-correct rate (text)"),
    ("wit_outcome_equiv", ("", False), "S1 strict, standard objects"),
    ("wit_outcome_equiv", ("", True), "S1 strict, probe objects"),
    ("wit_outcome_equiv", ("_relaxed", False), "S1 determined-only, standard objects"),
    ("wit_outcome_equiv", ("_relaxed", True), "S1 determined-only, probe objects"),
    ("wit_s2_ref", ("", False), "S2 on reference objects"),
    ("cost_usd", ("", False), "cost per item-run (US$)"),
    ("input_tokens", ("", False), "input tokens per item-run"),
    ("output_tokens", ("", False), "output tokens per item-run"),
]


def read(run: str, variant: tuple) -> pd.DataFrame:
    suffix, probe = variant
    d = pd.read_csv(RUNS_DIR / run / f"scores{suffix}{'_probe' if probe else ''}.csv")
    return d[d.ifc_only == 1].copy()


def per_item(runs: list[str], col: str, variant: tuple) -> pd.Series:
    frames = [read(r, variant).set_index("id")[col] for r in runs]
    return pd.concat(frames, axis=1).mean(axis=1, skipna=True)


def paired() -> pd.DataFrame:
    rows = []
    for col, variant, label in METRICS:
        a, b = per_item(RUN5, col, variant), per_item(RUN6, col, variant)
        items = sorted(set(a.dropna().index) & set(b.dropna().index))
        A, Bv = a.loc[items].to_numpy(float), b.loc[items].to_numpy(float)
        n = len(items)
        diff = float((Bv - A).mean())
        boots = []
        for _ in range(B):
            idx = RNG.integers(0, n, n)
            boots.append((Bv[idx] - A[idx]).mean())
        lo, hi = np.percentile(boots, [2.5, 97.5])
        rows.append({"measure": label, "items paired": n,
                     "run5_25flash": round(float(A.mean()), 4),
                     "run6_38flash": round(float(Bv.mean()), 4),
                     "difference": round(diff, 4), "ci_low": round(float(lo), 4),
                     "ci_high": round(float(hi), 4),
                     "excludes_zero": bool(lo > 0 or hi < 0)})
    return pd.DataFrame(rows)


def run6_both_ways():
    """The item-runs that hit the token ceiling, counted as failures and set aside."""
    budget = set()
    for run in RUN6:
        for line in open(RUNS_DIR / run / "log.jsonl", encoding="utf-8"):
            r = json.loads(line)
            if r.get("status") == "budget_exceeded":
                budget.add((run, r["id"]))
    rows = []
    for suffix, scoring in (("", "strict"), ("_relaxed", "determined-only")):
        for probe in (False, True):
            attempted = executed = exact = 0
            for run in RUN6:
                d = read(run, (suffix, probe))
                attempted += len(d)
                ex = d[d.wit_outcome_equiv.notna()]
                executed += len(ex)
                exact += int(ex.wit_outcome_equiv.sum())
            nb = len(budget)
            rows.append({"scoring": scoring, "object set": "probe" if probe else "standard",
                         "exact": exact,
                         "n_all_attempted": attempted,
                         "S1_budget_counted": round(exact / attempted, 4),
                         "n_budget_set_aside": attempted - nb,
                         "S1_budget_excluded": round(exact / (attempted - nb), 4),
                         "n_executed_only": executed,
                         "S1_executed_only": round(exact / executed, 4),
                         "budget_exceeded_item_runs": nb})
    return pd.DataFrame(rows), sorted(budget)


def omission() -> pd.DataFrame:
    """Reference asks for a value, the generated file leaves the property unconstrained."""
    def group_of(d):
        if d == "value":
            return "value not derivable from the request"
        if d == "facet":
            return "whole requirement not derivable"
        return "derivable from the request"

    rows = []
    for label, runs in (("Run 5 (2.5 Flash)", RUN5), ("Run 6 (3.8 Flash)", RUN6)):
        mp = matched_pairs(runs)
        mp = mp[mp.ref_has_value]
        for det, sub in mp.groupby(mp.determinacy.map(group_of)):
            om = ~sub.gen_has_value
            rows.append({"group": label, "reference value is": det,
                         "matched reqs with a reference value": len(sub),
                         "value omitted": int(om.sum()),
                         "omission rate": round(float(om.mean()), 3),
                         "value present but different": int((~om & ~sub.norm_agree).sum()),
                         "value present and equal": int((~om & sub.norm_agree).sum())})
        om = ~mp.gen_has_value
        rows.append({"group": label, "reference value is": "ALL",
                     "matched reqs with a reference value": len(mp),
                     "value omitted": int(om.sum()),
                     "omission rate": round(float(om.mean()), 3),
                     "value present but different": int((~om & ~mp.norm_agree).sum()),
                     "value present and equal": int((~om & mp.norm_agree).sum())})
    return pd.DataFrame(rows)


def cost() -> pd.DataFrame:
    rows = []
    for label, runs, price in (("Run 5 (2.5 Flash)", RUN5, "0.30 / 2.50 per 1M"),
                               ("Run 6 (3.8 Flash)", RUN6, "0.75 / 3.75 per 1M")):
        d = pd.concat([read(r, ("", False)) for r in runs])
        ok = d[d.status == "ok"]
        rows.append({"group": label, "list price in/out (US$)": price, "item_runs": len(d),
                     "mean cost per item-run": round(float(d.cost_usd.mean()), 4),
                     "mean cost per successful item-run": round(float(ok.cost_usd.mean()), 4),
                     "median input tokens": int(d.input_tokens.median()),
                     "median output tokens": int(d.output_tokens.median()),
                     "total logged cost": round(float(d.cost_usd.sum()), 2)})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = paired()
    p.to_csv(OUT / "r1_run6_vs_run5_paired.csv", index=False)
    print("=== 5. Run 6 (3.8 Flash) against Run 5 (2.5 Flash), paired by item")
    print("    (per-item means over that run's own repeats; 95% bootstrap CI on the difference)")
    print()
    for _, r in p.iterrows():
        star = " *" if r.excludes_zero else "  "
        print(f"  {r.measure:<38}{r.run5_25flash:>10.3f}{r.run6_38flash:>10.3f}"
              f"{r.difference:>+10.3f}  [{r.ci_low:>+8.3f},{r.ci_high:>+8.3f}]{star}"
              f"  n={r['items paired']}")

    bw, budget = run6_both_ways()
    bw.to_csv(OUT / "r2_run6_both_ways.csv", index=False)
    print()
    print("=== Run 6 with the token-ceiling failures counted and set aside")
    print(bw.to_string(index=False))
    print("  the item-runs that hit the 267,000-token ceiling:")
    for run, iid in budget:
        print(f"    {run}  {iid}")

    om = omission()
    om.to_csv(OUT / "r3_value_omission_by_determinacy.csv", index=False)
    print()
    print("=== value omission, split by whether the reference value is derivable")
    print(om.to_string(index=False))

    c = cost()
    c.to_csv(OUT / "r4_cost_per_item.csv", index=False)
    print()
    print("=== cost per item")
    print(c.to_string(index=False))
    print()
    print(f"wrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
