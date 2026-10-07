"""Text verdict against behaviour verdict, item-run by item-run (v8 section 3).

    python -m eval.analysis_pairs

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

Every row is one generated file judged twice: once by comparing its XML with the reference
(three classes, from strictest to loosest) and once by executing both files against the test
model. The question the table answers is the one the study is about -- how often the text
verdict and the behaviour verdict disagree, in both directions -- so the conditional
probabilities carry bootstrap intervals over items.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from eval.common import EVAL_DIR, RUNS_DIR

OUT = EVAL_DIR / "reports" / "v8"
GROUPS = {"Run 5 (2.5 Flash, 47 items x 3)": [f"run5-rep{r}" for r in (1, 2, 3)],
          "Run 6 (3.8 Flash, 47 items x 2)": ["run6-flash-rep1", "run6-flash-rep2"]}
CLASSES = ("text exact", "names correct, text not exact", "names wrong")
B = 2000
RNG = np.random.default_rng(20261007)


def rows(runs: list[str], relaxed: bool, probe: bool) -> pd.DataFrame:
    out = []
    for run in runs:
        f = RUNS_DIR / run / f"scores{'_relaxed' if relaxed else ''}{'_probe' if probe else ''}.csv"
        d = pd.read_csv(f)
        d = d[(d.ifc_only == 1) & d.wit_outcome_equiv.notna()]
        for _, r in d.iterrows():
            if r.facet_f1 == 1.0:
                cls = "text exact"
            elif r.names_correct == 1:
                cls = "names correct, text not exact"
            else:
                cls = "names wrong"
            out.append({"run": run, "id": r.id, "text_class": cls,
                        "text_exact": int(r.facet_f1 == 1.0),
                        "names_correct": int(r.names_correct),
                        "behaviour_exact": int(r.wit_outcome_equiv),
                        "facet_f1": r.facet_f1, "direction": r.wit_direction})
    return pd.DataFrame(out)


def ci(d: pd.DataFrame, mask: pd.Series) -> tuple:
    """P(behaviour exact | mask), bootstrapping ITEMS and carrying their repeats."""
    sub = d[mask]
    if not len(sub):
        return None, None, None, 0, 0
    per = {i: g.behaviour_exact.to_numpy(dtype=float) for i, g in sub.groupby("id")}
    ids = sorted(per)
    n = len(ids)
    point = float(np.mean([v for i in ids for v in per[i]]))
    boots = [np.mean([v for j in RNG.integers(0, n, n) for v in per[ids[j]]]) for _ in range(B)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi), len(sub), n


def table() -> pd.DataFrame:
    out = []
    for label, runs in GROUPS.items():
        for relaxed in (False, True):
            scoring = "determined-only" if relaxed else "strict"
            for probe in (False, True):
                d = rows(runs, relaxed, probe)
                for cls in CLASSES:
                    m = d.text_class == cls
                    est, lo, hi, n, ni = ci(d, m)
                    out.append({"group": label, "scoring": scoring,
                                "object set": "probe" if probe else "standard",
                                "text class": cls, "item_runs": n, "items": ni,
                                "behaviour exact": int((m & (d.behaviour_exact == 1)).sum()),
                                "behaviour differs": int((m & (d.behaviour_exact == 0)).sum()),
                                "P(behaviour exact)": None if est is None else round(est, 3),
                                "ci_low": None if lo is None else round(lo, 3),
                                "ci_high": None if hi is None else round(hi, 3)})
                # the two headline conditionals, stated explicitly
                for name, m in (("text exact (any)", d.text_exact == 1),
                                ("text NOT exact", d.text_exact == 0),
                                ("names wrong", d.names_correct == 0)):
                    est, lo, hi, n, ni = ci(d, m)
                    out.append({"group": label, "scoring": scoring,
                                "object set": "probe" if probe else "standard",
                                "text class": f"[conditional] {name}", "item_runs": n, "items": ni,
                                "behaviour exact": int((m & (d.behaviour_exact == 1)).sum()),
                                "behaviour differs": int((m & (d.behaviour_exact == 0)).sum()),
                                "P(behaviour exact)": None if est is None else round(est, 3),
                                "ci_low": None if lo is None else round(lo, 3),
                                "ci_high": None if hi is None else round(hi, 3)})
    return pd.DataFrame(out)


def disagreement_rate() -> pd.DataFrame:
    """How often the two verdicts disagree at all, and which way."""
    out = []
    for label, runs in GROUPS.items():
        for relaxed in (False, True):
            scoring = "determined-only" if relaxed else "strict"
            for probe in (False, True):
                d = rows(runs, relaxed, probe)
                tx, bh = d.text_exact == 1, d.behaviour_exact == 1
                out.append({"group": label, "scoring": scoring,
                            "object set": "probe" if probe else "standard",
                            "item_runs": len(d),
                            "both exact": int((tx & bh).sum()),
                            "text exact, behaviour differs": int((tx & ~bh).sum()),
                            "text differs, behaviour exact": int((~tx & bh).sum()),
                            "both differ": int((~tx & ~bh).sum()),
                            "disagreement rate": round(float(((tx & ~bh) | (~tx & bh)).mean()), 3)})
    return pd.DataFrame(out)


def sample_models() -> pd.DataFrame:
    """The same comparison on the two real sample buildings, which discriminate far less.

    vf0 = no version filtering, vf1 = ifctester filters specs by declared ifcVersion. An item-run
    counts only where the building actually exercised the specification.
    """
    out = []
    for label, runs in GROUPS.items():
        for relaxed in (False, True):
            scoring = "determined-only" if relaxed else "strict"
            for col, how in (("vf0_outcome_equiv", "sample buildings (no version filter)"),
                             ("vf1_outcome_equiv", "sample buildings (version filtered)")):
                frames = []
                for run in runs:
                    d = pd.read_csv(RUNS_DIR / run / f"scores{'_relaxed' if relaxed else ''}.csv")
                    frames.append(d[(d.ifc_only == 1) & d[col].notna()])
                d = pd.concat(frames)
                tx, bh = d.facet_f1 == 1.0, d[col] == 1
                out.append({"group": label, "scoring": scoring, "object set": how,
                            "item_runs": len(d),
                            "both exact": int((tx & bh).sum()),
                            "text exact, behaviour differs": int((tx & ~bh).sum()),
                            "text differs, behaviour exact": int((~tx & bh).sum()),
                            "both differ": int((tx.pipe(lambda x: ~x) & ~bh).sum()),
                            "disagreement rate": round(float(((tx & ~bh) | (~tx & bh)).mean()), 3)})
    return pd.DataFrame(out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = table()
    t.to_csv(OUT / "m1_text_class_x_behaviour.csv", index=False)
    print("=== 3. text class against behaviour, with 95% bootstrap intervals over items\n")
    for label in GROUPS:
        for scoring in ("strict", "determined-only"):
            for obj in ("standard", "probe"):
                sub = t[(t.group == label) & (t.scoring == scoring) & (t["object set"] == obj)]
                print(f"  {label} | {scoring} | {obj} objects")
                for _, r in sub.iterrows():
                    p = r["P(behaviour exact)"]
                    ps = "   n/a " if p is None else f"{p:>6.3f}"
                    cis = "" if p is None else f"  [{r.ci_low:.3f},{r.ci_high:.3f}]"
                    print(f"    {r['text class']:<36}{r['behaviour exact']:>4}/{r.item_runs:<4}"
                          f"P(behaviour exact) {ps}{cis}")
                print()
    dr = pd.concat([disagreement_rate(), sample_models()])
    dr.to_csv(OUT / "m2_disagreement_rate.csv", index=False)
    print("=== how often the two verdicts disagree at all, by how discriminating the model is")
    print(dr.to_string(index=False))
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
