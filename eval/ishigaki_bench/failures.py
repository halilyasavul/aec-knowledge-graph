"""Why Ishigaki item-runs fail: a mechanical per-facet comparison of gold and candidate.

    python -m eval.ishigaki_bench.failures

Read-only. For every scored item-run that is not behaviour-exact (S1, probe set), each gold
requirement is matched to the candidate by identity (property set + name, attribute name, ...),
and every difference gets one cause:

  mapped_to_standard  the gold keeps the request's words in a user-defined set
                      (^(?!(Pset_|Qto_)).+ or a named custom set) and the candidate has no such
                      property, but adds a standard Pset_/Qto_ property instead
  missing / extra     a requirement on one side only (after the mapping above is counted)
  value / datatype / cardinality   a matched requirement that differs there
  applicability       the specifications' applicability differs (entity, predefinedType, or the
                      attribute/property facets of stage 2)

Writes eval/reports/v9/h5_ishigaki_failure_causes.csv (one row per item-run) and prints counts.
"""
from __future__ import annotations

import json
from collections import Counter

import pandas as pd
from lxml import etree

from eval import score as S
from eval.common import EVAL_DIR, RUNS_DIR, safe_name
from eval.ishigaki_bench.analysis import GROUPS, TASKS
from eval.nl_to_ids_testset.extract_testset import Q, facet_target

OUT = EVAL_DIR / "reports" / "v9"


def _facets(xml: bytes) -> tuple[list, list]:
    root = etree.fromstring(xml)
    app, req = [], []
    for sp in root.iter(Q("specification")):
        a = sp.find(Q("applicability"))
        app.append(tuple(sorted(S.canon(facet_target(c)) for c in a if isinstance(c.tag, str))) if a is not None else ())
        r = sp.find(Q("requirements"))
        req += [facet_target(c) for c in r if isinstance(c.tag, str)] if r is not None else []
    return app, req


def _user_pset(f: dict) -> bool:
    ps = f.get("propertySet") or ""
    return f["facet"] == "property" and not ps.startswith(("Pset_", "Qto_"))


def _name(f: dict) -> str:
    ps = f.get("propertySet") or ""
    ps = "<user set>" if ps.startswith("RESTRICTION(") else ps
    return f"{ps}.{f.get('baseName')}" if f["facet"] == "property" else f"{f['facet']} {f.get('name') or f.get('system') or f.get('entity') or ''}"


def causes(gold: bytes, cand: bytes, notes: list | None = None) -> Counter:
    """Counter of causes; `notes`, if given, receives one short phrase per difference."""
    notes = notes if notes is not None else []
    g_app, g_req = _facets(gold)
    c_app, c_req = _facets(cand)
    out: Counter = Counter()
    if sorted(g_app) != sorted(c_app):
        out["applicability"] += 1
        notes.append(f"applicability: {len(g_app)} gold spec(s) vs {len(c_app)}; gold facets "
                     f"{sorted({x[0][1] for a in g_app for x in a})}, candidate {sorted({x[0][1] for a in c_app for x in a})}")
    by_key = {}
    for f in c_req:
        by_key.setdefault(S.loose_key(f), []).append(f)
    unmatched_gold = []
    for f in g_req:
        hits = by_key.get(S.loose_key(f))
        if not hits:
            unmatched_gold.append(f)
            continue
        c = hits.pop(0)
        if not hits:
            by_key.pop(S.loose_key(f))
        if S.canon_value(f["facet"], "value", f.get("value")) != S.canon_value(c["facet"], "value", c.get("value")):
            out["value"] += 1
            notes.append(f"value {_name(f)}: {f.get('value')} vs {c.get('value')}")
        if (f.get("dataType") or "").upper() != (c.get("dataType") or "").upper():
            out["datatype"] += 1
            notes.append(f"dataType {_name(f)}: {f.get('dataType')} vs {c.get('dataType')}")
        if (f.get("cardinality") or "required") != (c.get("cardinality") or "required"):
            out["cardinality"] += 1
            notes.append(f"cardinality {_name(f)}: {f.get('cardinality')} vs {c.get('cardinality')}")
    extra = [c for v in by_key.values() for c in v]
    std_extra = [c for c in extra if c["facet"] == "property" and (c.get("propertySet") or "").startswith(("Pset_", "Qto_"))]
    for f in unmatched_gold:
        if _user_pset(f) and std_extra:
            c = std_extra.pop(0)
            extra.remove(c)
            out["mapped_to_standard"] += 1
            notes.append(f"mapped '{f.get('baseName')}' -> {c.get('propertySet')}.{c.get('baseName')}")
        else:
            out["missing"] += 1
            notes.append(f"missing {_name(f)}")
    out["extra"] += len(extra)
    notes += [f"extra {_name(c)}" for c in extra]
    return out


def main():
    tasks = {json.loads(l)["id"]: json.loads(l) for l in open(TASKS, encoding="utf-8")}
    rows = []
    for model, stages in GROUPS.items():
        for stage, runs in stages.items():
            for run in runs:
                f = RUNS_DIR / run / "scores_probe.csv"
                if not f.exists():
                    continue
                for _, r in pd.read_csv(f).iterrows():
                    it = tasks[r["id"]]
                    p = RUNS_DIR / run / "generated" / f"{safe_name(r['id'])}.ids"
                    notes: list = []
                    c = causes(it["gold_ids"].encode("utf-8"), p.read_bytes(), notes) if p.exists() else Counter({"no_file": 1})
                    v = r["wit_outcome_equiv"]
                    rows.append({"model": model, "stage": stage, "run": run, "id": r["id"],
                                 "input_format": it["input_format"],
                                 "verdict": "unverified" if pd.isna(v) else ("exact" if v == 1 else "failing"),
                                 "direction": r.get("wit_direction"), **{k: c.get(k, 0) for k in (
                                     "mapped_to_standard", "missing", "extra", "value", "datatype", "cardinality",
                                     "applicability", "no_file")},
                                 "first_diverging": str(r.get("wit_diverging") or "").split(" ")[0],
                                 "differences": " | ".join(notes)})
    d = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "h5_ishigaki_failure_causes.csv", index=False)
    kinds = ["mapped_to_standard", "missing", "extra", "value", "datatype", "cardinality", "applicability", "no_file"]
    for (model, stage), g in d.groupby(["model", "stage"]):
        fail = g[g.verdict == "failing"]
        print(f"\n{model} {stage}: {len(fail)} failing of {len(g)} item-runs ({(g.verdict == 'unverified').sum()} unverified)")
        print("  item-runs with the cause:", {k: int((fail[k] > 0).sum()) for k in kinds})
        print("  facet differences:      ", {k: int(fail[k].sum()) for k in kinds})
        only = fail[(fail.mapped_to_standard > 0) & (fail[[k for k in kinds if k != "mapped_to_standard"]].sum(axis=1) == 0)]
        print(f"  failing ONLY because of mapping to standard sets: {len(only)}")
    print(f"\n-> {OUT / 'h5_ishigaki_failure_causes.csv'}")


if __name__ == "__main__":
    main()
