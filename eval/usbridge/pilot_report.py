"""Tables for the v10b pilot: one per granularity x condition, paired comparison, failure
classes, cost and tokens. Reads eval/runs/<run>/log.jsonl and <run>/usbridge_scores/ (written by
eval.usbridge.score_usbridge). Writes eval/usbridge/summary/pilot.json (totals only).

    python -X utf8 -m eval.usbridge.pilot_report usbridge-pilot-ifc usbridge-pilot-ifc-usbridge
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
RUNS = ROOT.parent / "runs"
RNG = np.random.default_rng(20261104)
B = 2000


def load_log(run: str) -> dict:
    out = {}
    for line in open(RUNS / run / "log.jsonl", encoding="utf-8"):
        r = json.loads(line)
        out[r["id"]] = r                                  # last attempt wins
    return out


def ci(values: list[float]) -> tuple:
    v = np.array([x for x in values if x is not None], dtype=float)
    if not len(v):
        return (None, None, None, 0)
    boots = [v[RNG.integers(0, len(v), len(v))].mean() for _ in range(B)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (float(v.mean()), float(lo), float(hi), len(v))


def num(x):
    return float(x) if x not in (None, "") else None


def run_tables(run: str) -> dict:
    log = load_log(run)
    sc = RUNS / run / "usbridge_scores"
    summ = json.loads((sc / "summary.json").read_text(encoding="utf-8"))
    rows_b = {r["id"]: r for r in csv.DictReader(open(sc / "b" / "scores.csv", encoding="utf-8"))}
    rows_a = {r["id"]: r for r in csv.DictReader(open(sc / "setlevel.csv", encoding="utf-8"))}
    ent = [i for i in log if i != "usb-section4"]
    s1 = {i: num(rows_b[i].get("wit_outcome_equiv")) for i in rows_b}
    cost = [log[i].get("cost_usd") or 0 for i in log]
    from eval import score
    from eval.common import safe_name
    def usb_out(i):                                       # the generated file names a usBridge set
        p = RUNS / run / "generated" / f"{safe_name(i)}.ids"
        return p.exists() and any(str(f.get("propertySet") or "").startswith("usBr")
                                  for f in score.parse_candidate(p)["requirements"])
    def usb_lookups(i):
        return sum(1 for c in log[i].get("tool_calls") or [] if c["tool"] == "query_pset"
                   and str((c.get("args") or {}).get("pset_code", "")).startswith("usBr"))
    custom = {}
    for i in ent:
        p = RUNS / run / "generated" / f"{safe_name(i)}.ids"
        if p.exists():
            fs = score.parse_candidate(p)["requirements"]
            custom[i] = sum(1 for f in fs if f["facet"] == "property"
                            and not str(f.get("propertySet") or "").startswith(("Pset_", "Qto_", "usBr")))
    def med(key, ids):
        xs = [log[i].get(key) for i in ids if log[i].get(key) is not None]
        return st.median(xs) if xs else None
    return {
        "items": len(log), "ok": sum(1 for r in log.values() if r["status"] == "ok"),
        "no_file": sum(1 for r in log.values() if r["status"] == "no_file"),
        "error": sum(1 for r in log.values() if r["status"] == "error"),
        "b_s1_entity": ci([s1[i] for i in s1 if i != "usb-section4"]),
        "b_s1_document": s1.get("usb-section4"),
        "b_facet_f1_micro": summ["b"]["facet_f1_micro"],
        "b_facet_f1_entity_mean": ci([num(rows_b[i].get("facet_f1")) for i in rows_b if i != "usb-section4"]),
        "a_facet_f1_micro": summ["a"]["facet_f1_micro"],
        "a_facet_f1_entity_mean": ci([num(rows_a[i]["a_f1"]) for i in rows_a if i != "usb-section4"]),
        "a_facet_f1_document": num(rows_a.get("usb-section4", {}).get("a_f1")),
        "a_spec_match_entity": ci([num(rows_a[i]["a_spec_match"]) for i in rows_a if i != "usb-section4"]),
        "strict": summ.get("strict"),
        "failure_classes": summ["failure_classes"],
        "cost_total": sum(cost), "cost_per_entity_item_mean": st.mean([log[i].get("cost_usd") or 0 for i in ent]),
        "cost_document": (log.get("usb-section4") or {}).get("cost_usd"),
        "cost_first10_max": max([log[i].get("cost_usd") or 0 for i in ent[:10]], default=None),
        "input_tokens_median": med("input_tokens", ent), "output_tokens_median": med("output_tokens", ent),
        "thinking_tokens_median": med("thinking_tokens", ent),
        "tool_calls_median": st.median([len(log[i].get("tool_calls") or []) for i in ent]),
        "wall_s_median": (med("wall_ms", ent) or 0) / 1000,
        "items_output_with_usbrpset": sum(1 for i in ent if usb_out(i)),
        "items_with_usbrpset_lookup": sum(1 for i in ent if usb_lookups(i)),
        "usbrpset_lookups_total": sum(usb_lookups(i) for i in ent),
        "items_with_custom_psets": sum(1 for v in custom.values() if v),
        "custom_pset_property_facets": sum(custom.values()),
        "s1_by_item": s1,
        "a_f1_by_item": {i: num(rows_a[i]["a_f1"]) for i in rows_a},
    }


def paired(x: dict, y: dict) -> dict:
    ids = [i for i in x if i in y and x[i] is not None and y[i] is not None]
    return {"n": len(ids), "better": sum(1 for i in ids if y[i] > x[i]), "worse": sum(1 for i in ids if y[i] < x[i]),
            "same": sum(1 for i in ids if y[i] == x[i])}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    base, usb = argv[:2]
    t = {base: run_tables(base), usb: run_tables(usb)}
    out = {"conditions": {base: "ifc", usb: "ifc,usbridge"},
           "tables": {k: {kk: vv for kk, vv in v.items() if not kk.endswith("_by_item")} for k, v in t.items()},
           "paired_b_s1": paired(t[base]["s1_by_item"], t[usb]["s1_by_item"]),
           "paired_a_f1": paired(t[base]["a_f1_by_item"], t[usb]["a_f1_by_item"])}
    (ROOT / "summary").mkdir(exist_ok=True)
    (ROOT / "summary" / "pilot.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
