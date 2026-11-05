"""Score a usBridge run at the two granularities of eval/reports/v10/scoring_plan.md.

    python -X utf8 -m eval.usbridge.score_usbridge eval/runs/<run>          # score a generated run
    python -X utf8 -m eval.usbridge.score_usbridge --gate                   # reference vs reference

(a) set-level   reference = the item's specs as published (specs.jsonl, corrected, unexpanded);
                candidate projected to set level; units per spec = (entity, predefinedType) + facet key;
                micro facet P/R/F1 and spec match. Implemented here.
(b) determined  reference = expanded specs kept to the facets an IDM-1 row states
                (annotations/determinacy.jsonl), values dropped where only the value is undetermined,
                empty specs dropped; where HDR made a determined facet optional the candidate's
                cardinality is adopted. Scored by eval.score unchanged (S1 on the witness model,
                facet F1), with eval.witness.EXTENSIONS on.
Failure classes are counted on (b). Writes <out>/setlevel.csv, <out>/b/scores.csv, <out>/summary.json.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from eval import score, witness
from eval.common import safe_name
from eval.usbridge.harness_check import clean

ROOT = Path(__file__).resolve().parent
RUNS = ROOT.parent / "runs"
MODELS = ROOT.parent / "models"


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


# --------------------------------------------------------------------------- (b) determined subset
def tasks_b(items: list[dict], specs: dict, det: dict) -> tuple[list[dict], list[str]]:
    out, empty = [], []
    for it in items:
        sps = []
        for sid in it["reference_spec_ids"]:
            sp = specs[sid]
            kept = []
            for f in sp["requirements"]:
                a = det.get((it["id"], sid, f["req_index"]))
                if not a or not a["determined"]:
                    continue
                g = clean(f)
                if a.get("scope") == "value":
                    g.pop("value", None)
                if a.get("cardinality_conflict"):
                    g["cardinality_free"] = True
                kept.append(g)
            if kept:
                sps.append({"spec_id": sid, "spec_name": sp["name"],
                            "applicability_facets": [clean(f) for f in sp["applicability"]["facets"]],
                            "target": kept})
        if not sps:
            empty.append(it["id"])
            continue
        first = next((specs[s["spec_id"]]["applies_to"] for s in sps if specs[s["spec_id"]]["applies_to"]), {}) or {}
        out.append({"id": it["id"], "source": "usbridge", "spec_name": it["id"],
                    "applicability": {"entity": first.get("entity"),
                                      **({"predefinedType": first["predefinedType"]} if first.get("predefinedType") else {})},
                    "target": [f for s in sps for f in s["target"]], "specs": sps,
                    "reference_spec_ids": [s["spec_id"] for s in sps]})
    return out, empty


def adopt(task: dict, cand: dict | None) -> dict:
    """Give each cardinality_free facet the cardinality of the candidate facet with its identity,
    looked up in the candidate specification with the same applicability (the same property can be
    required in one specification and optional in another); pooled only if no such specification."""
    pooled = {score.loose_key(c): c for c in (cand or {}).get("requirements", [])}
    per_app = {}
    for cs in (cand or {}).get("specs") or []:
        per_app.setdefault(app_key(cs["applicability_facets"]), {}).update(
            {score.loose_key(c): c for c in cs["target"]})
    def fix(f, by_key):
        g = {k: v for k, v in f.items() if k != "cardinality_free"}
        c = by_key.get(score.loose_key(f)) if f.get("cardinality_free") else None
        if c is not None:
            g["cardinality"] = c.get("cardinality") or "required"
        return g
    specs = [{**s, "target": [fix(f, per_app.get(app_key(s["applicability_facets"]), pooled)) for f in s["target"]]}
             for s in task["specs"]]
    return {**task, "specs": specs, "target": [f for s in specs for f in s["target"]]}


# --------------------------------------------------------------------------- (a) set level
def app_key(facets: list[dict]) -> tuple:
    e = next((f for f in facets if f["facet"] == "entity"), {})
    ent = score.canon_value("entity", "name", e.get("name")) or ""
    pt = score.canon_value("entity", "predefinedType", e.get("predefinedType")) or ""
    return ent, pt


def set_units(app: tuple, reqs: list[dict]) -> set:
    units, psets = {(app, ("applies",))}, {}
    for f in reqs:
        k, card = f["facet"], (f.get("cardinality") or "required")
        if k == "property":
            psets.setdefault(f.get("propertySet") or "", []).append(card)
        elif k == "attribute":
            units.add((app, ("attribute", f.get("name"), card)))
        elif k == "partOf":
            units.add((app, ("partOf", score.canon_value("partOf", "entity", f.get("entity")),
                             f.get("entityPredefinedType") or "", " ".join((f.get("relation") or "").upper().split()))))
        elif k in ("classification", "material"):
            units.add((app, (k, card)))
        elif k == "entity":
            units.add((app, ("entity", score.canon_value("entity", "name", f.get("name")),
                             score.canon_value("entity", "predefinedType", f.get("predefinedType")) or "")))
    for ps, cards in psets.items():
        card = ("required" if "required" in cards else "prohibited" if set(cards) == {"prohibited"} else "optional")
        units.add((app, ("pset", ps, card)))
    return units


def ref_units_a(item: dict, specs_un: dict, app_det: dict | None = None) -> set:
    specs = [{"spec_id": sid, "applicability_facets": specs_un[sid]["applicability"]["facets"],
              "target": specs_un[sid]["requirements"]} for sid in item["reference_spec_ids"]]
    if app_det is not None:                       # untyped where the request does not state the type
        specs = relax_app({"id": item["id"], "specs": specs}, app_det)["specs"]
    out = set()
    for sp in specs:
        out |= set_units(app_key(sp["applicability_facets"]), sp["target"])
    return out


# --------------------------------------------------------------------------- applicability determinacy
def load_app_det() -> dict:
    """(item id, spec id) -> whether the IDM states the spec's predefined type
    (annotations/applicability.jsonl, eval/usbridge/applicability.py)."""
    return {(r["id"], r["spec_id"]): r["determined"] for r in load(ROOT / "annotations" / "applicability.jsonl")}


def relax_app(task: dict, app_det: dict) -> dict:
    """Drop the predefined type from the applicability of specs whose type the request does not
    state; specs that end up with the same applicability are merged (facets united)."""
    merged: dict = {}
    for s in task["specs"]:
        facets = s["applicability_facets"]
        if app_det.get((task["id"], s["spec_id"])) is False:
            facets = [{k: v for k, v in f.items() if not (f["facet"] == "entity" and k == "predefinedType")}
                      for f in facets]
        key = json.dumps(sorted(json.dumps(f, sort_keys=True) for f in facets))
        if key not in merged:
            merged[key] = {**s, "applicability_facets": facets, "target": [], "merged_from": []}
        m = merged[key]
        m["merged_from"].append(s["spec_id"])
        for f in s["target"]:                     # one facet per identity across the merged kinds
            lk = score.loose_key(f)
            g = next((x for x in m["target"] if score.loose_key(x) == lk), None)
            if g is None:
                m["target"].append(dict(f))
                continue
            cards = {g.get("cardinality") or "required", f.get("cardinality") or "required"}
            g["cardinality"] = ("required" if "required" in cards else
                                "prohibited" if cards == {"prohibited"} else "optional")
            for fld in ("value", "dataType"):     # kept only where every kind agrees
                if g.get(fld) != f.get(fld):
                    g.pop(fld, None)
            if f.get("cardinality_free"):
                g["cardinality_free"] = True
    specs = list(merged.values())
    first = next((f for f in specs[0]["applicability_facets"] if f["facet"] == "entity"), {})
    return {**task, "specs": specs, "target": [f for s in specs for f in s["target"]],
            "applicability": {"entity": first.get("name"),
                              **({"predefinedType": first["predefinedType"]} if first.get("predefinedType") else {})}}


def cand_units_a(cand: dict) -> set:
    out = set()
    for sp in cand.get("specs") or []:
        out |= set_units(app_key(sp["applicability_facets"]), sp["target"])
    return out


def score_a(items: list[dict], specs_un: dict, gen: Path, app_det: dict | None = None) -> list[dict]:
    rows = []
    for it in items:
        p = gen / f"{safe_name(it['id'])}.ids"
        cand = score.parse_candidate(p) if p.exists() else None
        R, C = ref_units_a(it, specs_un, app_det), (cand_units_a(cand) if cand else set())
        tp, fp, fn = len(R & C), len(C - R), len(R - C)
        ref_apps = {u[0] for u in R}
        cand_apps = {u[0] for u in C}
        rows.append({"id": it["id"], "status": "ok" if cand else "no_file", "a_tp": tp, "a_fp": fp, "a_fn": fn,
                     "a_f1": (2 * tp / (2 * tp + fp + fn)) if (tp + fp + fn) else 1.0,
                     "a_spec_match": len(ref_apps & cand_apps) / len(ref_apps) if ref_apps else None,
                     "a_ref_specs": len(ref_apps)})
    return rows


# --------------------------------------------------------------------------- failure classes on (b)
def failure_classes(task_b: dict, cand: dict | None, full_keys: set) -> Counter:
    """Per reference specification (determined facets), against the candidate specification with
    the same (entity, predefinedType):
      entity_mapping          reference specs with no such candidate spec (their facets are
                              counted apart as facets_under_unmapped_entity)
      cardinality / value_or_datatype   same facet identity, that field differs
      pset_choice             the property is there under another set
      property_name           the set is there, the property name is not in it
      missing_facet           none of the above
      extra_facet             candidate facets (in any spec) whose identity is in no reference spec
                              of the item, determined or not
    """
    c = Counter()
    if cand is None:
        c["no_file"] += 1
        return c
    by_app: dict = {}
    for s in cand.get("specs") or []:
        by_app.setdefault(app_key(s["applicability_facets"]), []).extend(s["target"])
    for s in task_b["specs"]:
        creq = by_app.get(app_key(s["applicability_facets"]))
        if creq is None:
            c["entity_mapping"] += 1
            c["facets_under_unmapped_entity"] += len(s["target"])
            continue
        ccanon = Counter(score.canon(f) for f in creq)
        cloose = {score.loose_key(f): f for f in creq}
        for f in s["target"]:
            if ccanon[score.canon(f)] > 0:
                ccanon[score.canon(f)] -= 1
                c["correct"] += 1
                continue
            g = cloose.get(score.loose_key(f))
            if g is not None:
                c["cardinality" if (g.get("cardinality") or "required") != (f.get("cardinality") or "required")
                  else "value_or_datatype"] += 1
            elif f["facet"] == "property" and any(x["facet"] == "property" and x.get("baseName") == f.get("baseName")
                                                  for x in creq):
                c["pset_choice"] += 1
            elif f["facet"] == "property" and any(x["facet"] == "property" and x.get("propertySet") == f.get("propertySet")
                                                  for x in creq):
                c["property_name"] += 1
            else:
                c["missing_facet"] += 1
    c["extra_facet"] += sum(1 for f in cand["requirements"] if score.loose_key(f) not in full_keys)
    return c


def reclassify(run_dir: Path, items: list[dict]) -> dict:
    """Recompute the failure classes of a scored run (summary.json updated in place)."""
    out = run_dir / "usbridge_scores"
    specs_ex = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs_expanded.jsonl")}
    tb = {t["id"]: t for t in load(out / "b" / "tasks_b.jsonl")}
    classes = {}
    for iid, t in tb.items():
        p = run_dir / "generated" / f"{safe_name(iid)}.ids"
        cand = score.parse_candidate(p) if p.exists() else None
        item = next(i for i in items if i["id"] == iid)
        full = {score.loose_key(f) for sid in item["reference_spec_ids"] for f in specs_ex[sid]["requirements"]}
        classes[iid] = failure_classes(t, cand, full)
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    s["failure_classes"] = dict(sum(classes.values(), Counter()))
    s["per_item_classes"] = {k: dict(v) for k, v in classes.items()}
    (out / "summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s["failure_classes"]


# --------------------------------------------------------------------------- driver
def score_run(run_dir: Path, items: list[dict], out: Path | None = None, strict: bool = False,
              app: bool = False) -> dict:
    """app=True: the applicability-determinacy variant (annotations/applicability.jsonl); writes
    usbridge_scores_app/ beside the plan's usbridge_scores/."""
    out = out or run_dir / ("usbridge_scores_app" if app else "usbridge_scores")
    app_det = load_app_det() if app else None
    out.mkdir(parents=True, exist_ok=True)
    specs_un = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs.jsonl")}
    specs_ex = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs_expanded.jsonl")}
    det = {(r["id"], r["spec_id"], r["req_index"]): r for r in load(ROOT / "annotations" / "determinacy.jsonl")}
    gen = run_dir / "generated"
    rows_a = score_a(items, specs_un, gen, app_det)
    with open(out / "setlevel.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_a[0]))
        w.writeheader()
        w.writerows(rows_a)
    tb, empty = tasks_b(items, specs_ex, det)
    if app_det is not None:
        tb = [relax_app(t, app_det) for t in tb]
    adopted, classes = [], {}
    for t in tb:
        p = gen / f"{safe_name(t['id'])}.ids"
        cand = score.parse_candidate(p) if p.exists() else None
        adopted.append(adopt(t, cand))
        full = {score.loose_key(f) for sid in t["reference_spec_ids"] for f in specs_ex[sid]["requirements"]}
        full |= {score.loose_key(f) for sid in next(i for i in items if i["id"] == t["id"])["reference_spec_ids"]
                 for f in specs_ex[sid]["requirements"]}
        classes[t["id"]] = failure_classes(adopted[-1], cand, full)
    (out / "b").mkdir(exist_ok=True)
    tasks_path = out / "b" / "tasks_b.jsonl"
    with open(tasks_path, "w", encoding="utf-8") as fh:
        for t in adopted:
            fh.write(json.dumps(t) + "\n")
    witness.EXTENSIONS = True
    score.main([str(run_dir), str(tasks_path), str(MODELS), "--out", str(out / "b")])
    rows_b = list(csv.DictReader(open(out / "b" / "scores.csv", encoding="utf-8")))
    num = lambda r, k: float(r[k]) if r.get(k) not in (None, "") else None
    s1 = [num(r, "wit_outcome_equiv") for r in rows_b]
    summ = {
        "items": len(items), "b_items_scored": len(rows_b), "b_items_without_determined_facets": empty,
        "a": {"files": sum(r["status"] == "ok" for r in rows_a),
              "facet_tp": sum(r["a_tp"] for r in rows_a), "facet_fp": sum(r["a_fp"] for r in rows_a),
              "facet_fn": sum(r["a_fn"] for r in rows_a),
              "spec_match_mean": _mean([r["a_spec_match"] for r in rows_a if r["a_spec_match"] is not None])},
        "b": {"s1": sum(1 for x in s1 if x == 1.0), "s1_scored": sum(1 for x in s1 if x is not None),
              "witness_unverified": sum(1 for r in rows_b if r.get("wit_direction") == "witness_unverified"),
              "facet_f1_mean": _mean([num(r, "facet_f1") for r in rows_b]),
              "facet_tp": sum(int(r.get("facet_tp") or 0) for r in rows_b),
              "facet_fp": sum(int(r.get("facet_fp") or 0) for r in rows_b),
              "facet_fn": sum(int(r.get("facet_fn") or 0) for r in rows_b)},
        "failure_classes": dict(sum(classes.values(), Counter())),
    }
    if strict:                                   # appendix: the full expanded reference, nothing relaxed
        from eval.usbridge.harness_check import task as task_full
        (out / "strict").mkdir(exist_ok=True)
        sp = out / "strict" / "tasks_strict.jsonl"
        with open(sp, "w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(task_full(it, specs_ex)) + "\n")
        score.main([str(run_dir), str(sp), str(MODELS), "--out", str(out / "strict")])
        rs = list(csv.DictReader(open(out / "strict" / "scores.csv", encoding="utf-8")))
        tp, fp, fn = (sum(int(r.get(k) or 0) for r in rs) for k in ("facet_tp", "facet_fp", "facet_fn"))
        summ["strict"] = {"s1": sum(1 for r in rs if num(r, "wit_outcome_equiv") == 1.0),
                          "s1_scored": sum(1 for r in rs if num(r, "wit_outcome_equiv") is not None),
                          "facet_tp": tp, "facet_fp": fp, "facet_fn": fn,
                          "facet_f1_micro": 2 * tp / (2 * tp + fp + fn) if tp else 0.0}
    a = summ["a"]
    a["facet_f1_micro"] = 2 * a["facet_tp"] / (2 * a["facet_tp"] + a["facet_fp"] + a["facet_fn"]) if a["facet_tp"] else 0.0
    b = summ["b"]
    b["facet_f1_micro"] = 2 * b["facet_tp"] / (2 * b["facet_tp"] + b["facet_fp"] + b["facet_fn"]) if b["facet_tp"] else 0.0
    (out / "summary.json").write_text(json.dumps({**summ, "per_item_classes": {k: dict(v) for k, v in classes.items()}},
                                                 indent=1), encoding="utf-8")
    return summ


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def gate(items: list[dict]) -> dict:
    """Reference vs reference at both granularities: (a) the published specs as the candidate,
    (b) the determined reference as the candidate."""
    specs_un = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs.jsonl")}
    specs_ex = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs_expanded.jsonl")}
    det = {(r["id"], r["spec_id"], r["req_index"]): r for r in load(ROOT / "annotations" / "determinacy.jsonl")}
    from eval.usbridge.harness_check import task as task_un
    res = {}
    # (a): candidate = the published (corrected) specs, rebuilt by the scorer's own writer
    run_a = RUNS / "usbridge-gate-a"
    (run_a / "generated").mkdir(parents=True, exist_ok=True)
    for it in items:
        (run_a / "generated" / f"{safe_name(it['id'])}.ids").write_bytes(score.build_reference(task_un(it, specs_un)))
    rows = score_a(items, specs_un, run_a / "generated")
    res["a"] = {"items": len(rows), "f1_1": sum(1 for r in rows if r["a_f1"] == 1.0),
                "spec_match_1": sum(1 for r in rows if r["a_spec_match"] == 1.0),
                "not_perfect": [r for r in rows if r["a_f1"] != 1.0][:10]}
    # (b): candidate = the determined reference itself
    run_b = RUNS / "usbridge-gate-b"
    (run_b / "generated").mkdir(parents=True, exist_ok=True)
    tb, empty = tasks_b(items, specs_ex, det)
    for t in tb:
        (run_b / "generated" / f"{safe_name(t['id'])}.ids").write_bytes(score.build_reference(adopt(t, None)))
    summ = score_run(run_b, items, run_b / "usbridge_scores")
    rows_b = list(csv.DictReader(open(run_b / "usbridge_scores" / "b" / "scores.csv", encoding="utf-8")))
    res["b"] = {**summ["b"], "items_without_determined_facets": empty,
                "not_perfect": [{k: r.get(k) for k in ("id", "facet_f1", "wit_outcome_equiv", "wit_direction",
                                                       "wit_problems", "wit_unsupported")}
                                for r in rows_b if r.get("wit_outcome_equiv") not in ("1", "1.0")][:12]}
    (ROOT / "summary").mkdir(exist_ok=True)
    (ROOT / "summary" / "gate.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def gate_app(items: list[dict]) -> dict:
    """Reference vs reference for the applicability-determinacy variant, both granularities."""
    from eval.usbridge.harness_check import task as task_un
    specs_un = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs.jsonl")}
    specs_ex = {s["spec_id"]: s for s in load(ROOT / "reference" / "specs_expanded.jsonl")}
    det = {(r["id"], r["spec_id"], r["req_index"]): r for r in load(ROOT / "annotations" / "determinacy.jsonl")}
    app_det = load_app_det()
    res = {}
    run_a = RUNS / "usbridge-gate-a-app"
    (run_a / "generated").mkdir(parents=True, exist_ok=True)
    for it in items:
        t = task_un(it, specs_un)
        t = relax_app({**t, "specs": [{**s, "spec_id": sid} for s, sid in zip(t["specs"], t["reference_spec_ids"])]},
                      app_det)
        (run_a / "generated" / f"{safe_name(it['id'])}.ids").write_bytes(score.build_reference(t))
    rows = score_a(items, specs_un, run_a / "generated", app_det)
    res["a"] = {"items": len(rows), "f1_1": sum(1 for r in rows if r["a_f1"] == 1.0),
                "not_perfect": [r for r in rows if r["a_f1"] != 1.0][:10]}
    run_b = RUNS / "usbridge-gate-b-app"
    (run_b / "generated").mkdir(parents=True, exist_ok=True)
    tb, empty = tasks_b(items, specs_ex, det)
    for t in tb:
        (run_b / "generated" / f"{safe_name(t['id'])}.ids").write_bytes(score.build_reference(adopt(relax_app(t, app_det), None)))
    summ = score_run(run_b, items, app=True)
    rows_b = list(csv.DictReader(open(run_b / "usbridge_scores_app" / "b" / "scores.csv", encoding="utf-8")))
    res["b"] = {**summ["b"], "not_perfect": [{k: r.get(k) for k in ("id", "facet_f1", "wit_outcome_equiv", "wit_direction",
                                                                     "wit_problems")}
                                             for r in rows_b if r.get("wit_outcome_equiv") not in ("1", "1.0")][:12]}
    (ROOT / "summary" / "gate_app.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    items = load(ROOT / "items.jsonl")
    if argv and argv[0] == "--gate-app":
        r = gate_app(items)
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "not_perfect"} for k, v in r.items()}, indent=1))
        for k, v in r.items():
            for x in v["not_perfect"]:
                print(k, json.dumps(x)[:300])
        return
    if argv and argv[0] == "--gate":
        r = gate(items)
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "not_perfect"} for k, v in r.items()}, indent=1))
        for k, v in r.items():
            for x in v["not_perfect"]:
                print(k, json.dumps(x)[:300])
        return
    if argv and argv[0] == "--classes":
        for r in argv[1:]:
            print(r, json.dumps(reclassify(Path(r), items)))
        return
    run_dir = Path(argv[0])
    gen = run_dir / "generated"
    items = [it for it in items if (gen / f"{safe_name(it['id'])}.ids").exists()
             or (gen / f"{safe_name(it['id'])}.fail.json").exists()]          # the items this run attempted
    s = score_run(run_dir, items, strict="--strict" in argv, app="--app" in argv)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
