"""Held-out result tables for Ishigaki-IDS-Bench runs. Read-only; no model calls.

    python -m eval.ishigaki_bench.analysis

Writes eval/reports/v9/h1-h4. Ishigaki items are mostly not `ifc_only` (user-defined property
sets), so S1 is taken straight from scores*.csv over the rows where `wit_outcome_equiv` is not
null, with the same item bootstrap as the dev tables (eval.analysis_probe.rate_ci). There are
no determinacy or extras annotations: the requests were written so that the gold follows from
them, so strict scoring is the scoring.

FacetF1 "their way" follows eval/analysis_ishigaki.py (the v8 reading of IDS-Bench): one block
per facet keyed by side (applicability / requirements), facet type and constraint content, the
declared IFC versions as one more block, classification/material/partOf excluded, macro over
items, a missing file scoring 0 — here against the gold IDS itself, every specification.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd
from lxml import etree

from eval import score as S
from eval.analysis_probe import rate_ci
from eval.common import EVAL_DIR, RUNS_DIR, safe_name
from eval.nl_to_ids_testset.extract_testset import Q, facet_target

TASKS = EVAL_DIR / "ishigaki_bench" / "spec_tasks_en.jsonl"
OUT = EVAL_DIR / "reports" / "v9"
EXCLUDED = ("classification", "material", "partOf")
# model -> run directories (stage 1 and stage 2 runs of one model pool into one row per stage)
GROUPS = {"Sonnet 5.5": {"stage 1": ["run9-ishigaki-rep1"], "stage 2": ["run9-ishigaki-rep1-s2"]},
          "Opus": {"stage 1": ["run9-ishigaki-opus-rep1"], "stage 2": ["run9-ishigaki-opus-rep1-s2"]},
          # Run 10: the generator after Ishigaki stage 2 showed it could not select by attribute or
          # property in applicability -- not held-out clean for stage 2 (see heldout_summary.md)
          "Sonnet 5.5, Run 10 (+applicability facets)": {"stage 1": ["run10-ishigaki-rep1"],
                                                         "stage 2": ["run10-ishigaki-rep1-s2"]}}


def blocks(xml: bytes, with_version: bool) -> Counter:
    root = etree.fromstring(xml)
    c: Counter = Counter()
    versions = set()
    for sp in root.iter(Q("specification")):
        versions |= set((sp.get("ifcVersion") or "").split())
        for side in ("applicability", "requirements"):
            node = sp.find(Q(side))
            for f in ([x for x in node if isinstance(x.tag, str)] if node is not None else []):
                t = facet_target(f)
                if t["facet"] not in EXCLUDED:
                    c[(side, S.canon(t))] += 1
    if with_version:
        c[("ifcVersion", frozenset(versions))] += 1
    return c


def facetf1(item: dict, cand_path: Path, with_version: bool) -> float:
    R = blocks(item["gold_ids"].encode("utf-8"), with_version)
    if not cand_path.exists():
        return 0.0
    C = blocks(cand_path.read_bytes(), with_version)
    tp = sum((R & C).values())
    return S.prf(tp, sum(C.values()) - tp, sum(R.values()) - tp)[2]


def item_rows(run: str, tasks: dict) -> pd.DataFrame:
    d = RUNS_DIR / run
    if not (d / "scores.csv").exists():
        return pd.DataFrame()
    std = pd.read_csv(d / "scores.csv").set_index("id")
    prb = pd.read_csv(d / "scores_probe.csv").set_index("id") if (d / "scores_probe.csv").exists() else None
    rows = []
    for iid, r in std.iterrows():
        it = tasks[iid]
        p = d / "generated" / f"{safe_name(iid)}.ids"
        row = {"run": run, "id": iid, "input_format": it["input_format"], "domain": it["domain"],
               "n_specs": it["n_specs"], "turn_type": it["turn_type"], "status": r["status"],
               "xsd_valid": r.get("xsd_valid"), "facet_f1_ours": r["facet_f1"],
               "FacetF1_theirs": facetf1(it, p, True), "FacetF1_theirs_noversion": facetf1(it, p, False),
               "S1_standard": r["wit_outcome_equiv"], "direction_standard": r.get("wit_direction"),
               "diverging_standard": r.get("wit_diverging"), "cand_fail_reasons": r.get("cand_fail_reasons"),
               "ifc_version": r.get("ifc_version")}
        if prb is not None and iid in prb.index:
            q = prb.loc[iid]
            row.update({"S1_probe": q["wit_outcome_equiv"], "direction_probe": q.get("wit_direction"),
                        "diverging_probe": q.get("wit_diverging")})
        rows.append(row)
    return pd.DataFrame(rows)


def summarise(d: pd.DataFrame, label: dict) -> dict:
    out = {**label, "items": len(d), "ok": int((d.status == "ok").sum()), "no_file": int((d.status != "ok").sum())}
    for col in ("S1_standard", "S1_probe"):
        if col not in d or d[col].notna().sum() == 0:
            continue
        est, lo, hi, n_runs, n_items = rate_ci([d.rename(columns={col: "v"})[["id", "v"]]], "v")
        out.update({f"{col}": round(est, 4), f"{col}_ci_low": round(lo, 4), f"{col}_ci_high": round(hi, 4),
                    f"{col}_exact": int(d[col].fillna(0).sum()), f"{col}_verified": n_runs})
    out.update({"unverified": int(d.S1_standard.isna().sum()),
                "facet_f1_ours": round(float(d.facet_f1_ours.mean()), 4),
                "FacetF1_theirs": round(float(d.FacetF1_theirs.mean()), 4),
                "FacetF1_theirs_noversion": round(float(d.FacetF1_theirs_noversion.mean()), 4),
                "xsd_valid_rate": round(float((d.xsd_valid == 1).sum() / len(d)), 4) if len(d) else None})
    return out


def main():
    tasks = {json.loads(l)["id"]: json.loads(l) for l in open(TASKS, encoding="utf-8")}
    per_item, h1, h2 = [], [], []
    for model, stages in GROUPS.items():
        for stage, runs in stages.items():
            d = pd.concat([item_rows(r, tasks) for r in runs] or [pd.DataFrame()])
            if d.empty:
                continue
            per_item.append(d.assign(model=model, stage=stage))
            h1.append(summarise(d, {"model": model, "stage": stage}))
            for fmt, g in d.groupby("input_format"):
                h2.append(summarise(g, {"model": model, "stage": stage, "input_format": fmt}))
    if not per_item:
        print("no scored Ishigaki runs yet")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    items = pd.concat(per_item)
    pd.DataFrame(h1).to_csv(OUT / "h1_ishigaki_headline.csv", index=False)
    pd.DataFrame(h2).to_csv(OUT / "h2_ishigaki_by_format.csv", index=False)
    items.to_csv(OUT / "h3_ishigaki_items.csv", index=False)
    print(pd.DataFrame(h1).to_string(index=False))
    print(pd.DataFrame(h2)[["model", "stage", "input_format", "items", "S1_standard", "S1_probe",
                            "FacetF1_theirs", "FacetF1_theirs_noversion"]].to_string(index=False))
    # paired by item, Opus against Sonnet, per stage
    rows = []
    for stage in ("stage 1", "stage 2"):
        a = items[(items.model == "Sonnet 5.5") & (items.stage == stage)].set_index("id")
        b = items[(items.model == "Opus") & (items.stage == stage)].set_index("id")
        for iid in sorted(set(a.index) & set(b.index)):
            rows.append({"stage": stage, "id": iid, "input_format": a.loc[iid, "input_format"],
                         "sonnet_S1_probe": a.loc[iid].get("S1_probe"), "opus_S1_probe": b.loc[iid].get("S1_probe"),
                         "sonnet_S1_standard": a.loc[iid, "S1_standard"], "opus_S1_standard": b.loc[iid, "S1_standard"],
                         "sonnet_FacetF1": a.loc[iid, "FacetF1_theirs_noversion"],
                         "opus_FacetF1": b.loc[iid, "FacetF1_theirs_noversion"]})
    if rows:
        pr = pd.DataFrame(rows)
        pr.to_csv(OUT / "h4_ishigaki_opus_vs_sonnet.csv", index=False)
        for stage, g in pr.groupby("stage"):
            v = g.dropna(subset=["sonnet_S1_probe", "opus_S1_probe"])
            print(f"{stage}: Opus better on {(v.opus_S1_probe > v.sonnet_S1_probe).sum()}, worse on "
                  f"{(v.opus_S1_probe < v.sonnet_S1_probe).sum()} of {len(v)} verified items (S1, probe)")
    print(f"wrote h1-h4 to {OUT}")


if __name__ == "__main__":
    main()
