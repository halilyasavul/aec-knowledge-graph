"""Generated requirements the reference lacks: faithful to the request, or a defect? (v9 §A)

    python -m eval.analysis_extras

Read-only; no model calls. Writes CSVs to eval/reports/v9/.

The prompts are the IDS files' own description text, and for the Vienna set that text is
modelling guidance the authors never encoded as facets ("max. Polygonanzahl 10.000", "Typen
gemäss IfcSanitaryTerminalTypeEnum", the ÖNORM B 1800 room rules). A generator that follows
the request therefore emits requirements the reference does not have, and strict and
determined-only scoring both count them as failures. `eval/annotations/extras.jsonl` labels
every such (item, requirement) pair seen in Run 5 and Run 6 as `faithful` (the request
supports it) or `defect` (it does not). `python -m eval.score --excuse-extras` removes the
faithful ones from the candidate before scoring — the mirror image of `--relaxed`, which
removes undetermined facets from the reference — and writes `scores_relaxed_excused*.csv`.
"""
from __future__ import annotations

import json

import pandas as pd

from eval.analysis_probe import GROUPS, rate_ci
from eval.common import EVAL_DIR, RUNS_DIR

OUT = EVAL_DIR / "reports" / "v9"
LABELS = EVAL_DIR / "annotations" / "extras.jsonl"
SCORINGS = {"strict": "", "determined-only": "_relaxed",
            "determined-only, faithful extras excused": "_relaxed_excused",
            "request-determined (+PDF Status values), faithful extras excused": "_relaxed_rv_excused"}


def read(run: str, suffix: str, probe: bool) -> pd.DataFrame:
    d = pd.read_csv(RUNS_DIR / run / f"scores{suffix}{'_probe' if probe else ''}.csv")
    return d[d.ifc_only == 1].copy()


def labels() -> pd.DataFrame:
    rows = [json.loads(l) for l in open(LABELS, encoding="utf-8")]
    return pd.DataFrame([{"id": r["id"], "requirement": " ".join(r["key"]), "label": r["label"],
                          "reason": r["reason"], "runs_seen": " ".join(r["runs_seen"]),
                          "n_item_runs": len(r["runs_seen"])} for r in rows])


def headline() -> pd.DataFrame:
    rows = []
    for group, runs in GROUPS.items():
        for scoring, suffix in SCORINGS.items():
            for probe in (False, True):
                frames = [read(r, suffix, probe) for r in runs]
                est, lo, hi, n_runs, n_items = rate_ci(frames, "wit_outcome_equiv")
                s2, s2lo, s2hi, _, _ = rate_ci(frames, "wit_s2_ref")
                d = pd.concat(frames)
                rows.append({"group": group, "scoring": scoring, "object set": "probe" if probe else "standard",
                             "item_runs": n_runs, "items": n_items,
                             "S1": round(est, 4), "S1_ci_low": round(lo, 4), "S1_ci_high": round(hi, 4),
                             "S1_exact_count": int(d["wit_outcome_equiv"].fillna(0).sum()),
                             "S2_ref": round(s2, 4), "S2_ci_low": round(s2lo, 4), "S2_ci_high": round(s2hi, 4),
                             "facet_F1_mean": round(float(d["facet_f1"].mean()), 4),
                             "item_runs_with_excused": int((d.get("n_excused", pd.Series(0, index=d.index)).fillna(0) > 0).sum())})
    return pd.DataFrame(rows)


def flips() -> pd.DataFrame:
    rows = []
    for group, runs in GROUPS.items():
        for run in runs:
            for probe in (False, True):
                a = read(run, "_relaxed", probe).set_index("id")
                b = read(run, "_relaxed_excused", probe).set_index("id")
                for i in a.index:
                    if i not in b.index or not b.loc[i, "n_excused"]:
                        continue
                    rows.append({"group": group, "run": run, "object set": "probe" if probe else "standard", "id": i,
                                 "n_excused": int(b.loc[i, "n_excused"]),
                                 "S1_determined_only": a.loc[i, "wit_outcome_equiv"],
                                 "S1_excused": b.loc[i, "wit_outcome_equiv"],
                                 "direction_before": a.loc[i, "wit_direction"], "direction_after": b.loc[i, "wit_direction"],
                                 "facet_f1_before": round(a.loc[i, "facet_f1"], 3), "facet_f1_after": round(b.loc[i, "facet_f1"], 3),
                                 "verdict_changed": int(pd.notna(a.loc[i, "wit_outcome_equiv"]) and
                                                        a.loc[i, "wit_outcome_equiv"] != b.loc[i, "wit_outcome_equiv"])})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lab = labels()
    lab.to_csv(OUT / "e1_extras_labels.csv", index=False)
    print(f"e1: {len(lab)} labelled extras: {lab.label.value_counts().to_dict()}")
    h = headline()
    h.to_csv(OUT / "e2_headline_three_scorings.csv", index=False)
    print(h[["group", "scoring", "object set", "item_runs", "S1_exact_count", "S1", "S1_ci_low", "S1_ci_high", "facet_F1_mean"]].to_string(index=False))
    f = flips()
    f.to_csv(OUT / "e3_excused_item_runs.csv", index=False)
    print(f"e3: {len(f)} item-run x object-set rows touched by excusal; verdict changed in {int(f.verdict_changed.sum())}")


if __name__ == "__main__":
    main()
