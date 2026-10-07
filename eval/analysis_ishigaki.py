"""A FacetF1 column computed the way IDS-Bench computes it (v8 section 6).

    python -m eval.analysis_ishigaki

Read-only; no model calls. Writes CSVs to eval/reports/v8/.

IDS-Bench (arXiv 2605.22079) scores a generated IDS by matching blocks against the reference:
one block per facet, keyed by the side it sits on (applicability or requirements), the facet
type and the constraint content, with the declared IFC version counted as its own block. It
macro-averages the per-item F1. It reports no classification, material or partOf facets, so
those are excluded here too.

Caveat that has to travel with the number: our reference is reconstructed from the German IDS
files and declares all three IFC versions (IFC2X3 IFC4 IFC4X3_ADD2) so that the reference itself
is never version-filtered. A generated file that declares IFC4X3_ADD2 alone therefore loses the
version block even though it names the schema the request asked for. The table reports FacetF1
with and without that block for exactly that reason.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from eval import score as S
from eval.common import EVAL_DIR, RUNS_DIR, SPEC_TASKS, load_tasks, safe_name

OUT = EVAL_DIR / "reports" / "v8"
EXCLUDED = ("classification", "material", "partOf")
ALL_VERSIONS = frozenset(("IFC2X3", "IFC4", "IFC4X3_ADD2"))
GROUPS = {"Run 5 (2.5 Flash, 47 items x 3)": [f"run5-rep{r}" for r in (1, 2, 3)],
          "Run 6 (3.8 Flash, 47 items x 2)": ["run6-flash-rep1", "run6-flash-rep2"],
          "2x2 cell lk1dt1 (all fixes, 21 items x 3)": [f"run6-lk1dt1-rep{r}" for r in (1, 2, 3)],
          "2x2 cell lk0dt0 (no fixes, 21 items x 3)": [f"run6-lk0dt0-rep{r}" for r in (1, 2, 3)]}
B = 2000
RNG = np.random.default_rng(20261007)


def ref_blocks(item: dict, with_version: bool) -> Counter:
    c: Counter = Counter()
    a = item["applicability"]
    c[("applicability", S.canon({"facet": "entity", "name": a["entity"],
                                 "predefinedType": a.get("predefinedType")}))] += 1
    for f in item["target"]:
        if f["facet"] in EXCLUDED:
            continue
        c[("requirements", S.canon(f))] += 1
    if with_version:
        c[("ifcVersion", ALL_VERSIONS)] += 1
    return c


def cand_blocks(cand: dict, with_version: bool) -> Counter:
    c: Counter = Counter()
    for f in cand["applicability"]:
        c[("applicability", S.canon(f))] += 1
    for f in cand["requirements"]:
        if f["facet"] in EXCLUDED:
            continue
        c[("requirements", S.canon(f))] += 1
    if with_version:
        vs = frozenset(v for s in cand["versions"] for v in s.split())
        c[("ifcVersion", vs)] += 1
    return c


def per_item(run: str, with_version: bool) -> pd.DataFrame:
    """One row per generated file: FacetF1 in the IDS-Bench sense."""
    tasks = {t["id"]: t for t in load_tasks(SPEC_TASKS)}
    scores = pd.read_csv(RUNS_DIR / run / "scores.csv")
    keep = set(scores[scores.ifc_only == 1].id)
    rows = []
    for iid, item in tasks.items():
        if iid not in keep:
            continue
        p = RUNS_DIR / run / "generated" / f"{safe_name(iid)}.ids"
        R = ref_blocks(item, with_version)
        if not p.exists():                       # no file at all: F1 = 0, as IDS-Bench would score it
            rows.append({"run": run, "id": iid, "tp": 0, "fp": 0, "fn": sum(R.values()), "f1": 0.0})
            continue
        C = cand_blocks(S.parse_candidate(p), with_version)
        tp = sum((R & C).values())
        fp, fn = sum(C.values()) - tp, sum(R.values()) - tp
        rows.append({"run": run, "id": iid, "tp": tp, "fp": fp, "fn": fn,
                     "f1": S.prf(tp, fp, fn)[2]})
    return pd.DataFrame(rows)


def rate_ci(d: pd.DataFrame, col: str) -> tuple[float, float, float]:
    per = {i: g[col].to_numpy(dtype=float) for i, g in d.groupby("id")}
    ids = sorted(per)
    n = len(ids)
    point = float(np.mean([v for i in ids for v in per[i]]))
    boots = [np.mean([v for j in RNG.integers(0, n, n) for v in per[ids[j]]]) for _ in range(B)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def table() -> pd.DataFrame:
    rows = []
    for label, runs in GROUPS.items():
        for with_version in (True, False):
            frames = [per_item(r, with_version) for r in runs]
            d = pd.concat(frames)
            est, lo, hi = rate_ci(d, "f1")
            own = []
            for r in runs:
                s = pd.read_csv(RUNS_DIR / r / "scores.csv")
                own.append(s[s.ifc_only == 1].facet_f1.mean())
            rows.append({"group": label,
                         "IFC-version block": "counted" if with_version else "excluded",
                         "item_runs": len(d), "items": d.id.nunique(),
                         "FacetF1_macro_IDSBench": round(est, 4),
                         "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                         "our_facet_f1_macro": round(float(np.mean(own)), 4)})
    return pd.DataFrame(rows)


def version_detail() -> pd.DataFrame:
    """How often the declared version matches the reference's three-version declaration."""
    rows = []
    for label, runs in GROUPS.items():
        counts: Counter = Counter()
        for run in runs:
            scores = pd.read_csv(RUNS_DIR / run / "scores.csv")
            for v in scores[scores.ifc_only == 1].ifc_version.fillna("(no file)"):
                counts[str(v)] += 1
        for v, n in counts.most_common():
            rows.append({"group": label, "declared ifcVersion": v, "item_runs": n,
                         "matches the reference declaration": v.strip() == "IFC2X3 IFC4 IFC4X3_ADD2"})
    return pd.DataFrame(rows)


def clarifications() -> pd.DataFrame:
    """Did the clarification questions land on the items whose detail is not derivable?

    A clarification question is a run where the model answered in prose instead of calling
    generate_ids. If the model were detecting under-specified requests, these would be the items
    carrying determinacy annotations. They are not.
    """
    ann: dict = {}
    for line in open(EVAL_DIR / "annotations" / "determinacy.jsonl", encoding="utf-8"):
        r = json.loads(line)
        ann.setdefault(r["id"], []).append(r["scope"])
    rows = []
    for f in sorted((EVAL_DIR / "reports").glob("v8/s3_nofile_items_*.csv")):
        d = pd.read_csv(f)
        sub = d[d.cause.astype(str).str.contains("clarif", case=False, na=False)]
        for _, r in sub.iterrows():
            iid = r.iloc[1]
            labs = ann.get(iid, [])
            rows.append({"run": r.iloc[0], "id": iid, "item_runs": 1,
                         "undetermined labels on this item": len(labs),
                         "label scopes": ", ".join(sorted(set(labs))) or "none",
                         "model said": str(r.iloc[-1])[:160]})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = table()
    t.to_csv(OUT / "i1_ishigaki_facetf1.csv", index=False)
    print("=== 6. FacetF1 computed the IDS-Bench way (macro over items, 95% bootstrap CI)\n")
    for _, r in t.iterrows():
        print(f"  {r.group:<44}version {r['IFC-version block']:<9}"
              f"FacetF1 {r.FacetF1_macro_IDSBench:>6.3f}  [{r.ci_low:.3f},{r.ci_high:.3f}]"
              f"   (our facet F1 macro {r.our_facet_f1_macro:.3f})")
    print("\n  IDS-Bench best zero-shot FacetF1 reported in the paper: 0.656")
    vd = version_detail()
    vd.to_csv(OUT / "i2_declared_versions.csv", index=False)
    print("\n=== declared ifcVersion, which the block above depends on")
    print(vd.to_string(index=False))

    cl = clarifications()
    cl.to_csv(OUT / "i3_clarification_questions.csv", index=False)
    print("\n=== clarification questions against determinacy")
    if len(cl):
        print(cl[["run", "id", "undetermined labels on this item", "label scopes"]].to_string(index=False))
        per_item = cl.groupby("id")["undetermined labels on this item"].first()
        print(f"  {len(cl)} clarification item-runs on {cl.id.nunique()} distinct items; "
              f"undetermined labels per item: {dict(per_item)}")
    else:
        print("  none found")
    print(f"\nwrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
