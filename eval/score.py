"""Step 3 — score generated IDS intensionally (facet F1) and extensionally (verdicts).

    python -m eval.score <run_dir> <tasks.jsonl> <models_dir>

Writes <run_dir>/scores.csv (one row per item), <run_dir>/pairs.csv (one row per
item x model x version-mode), <run_dir>/reference/ (the reconstructed reference IDS) and
<run_dir>/witness/ (the witness models).

Extensional scoring is done on three surfaces:
  wit  a witness model built from the reference alone (eval/witness.py): elements that
       satisfy it, break one requirement each, or sit just outside its applicability.
       ifcVersion ignored at execution. This is the surface that can see property errors.
  vf0  sample models, should_filter_version=False — ifcVersion ignored. The models are
       only a surface for disagreement, so a candidate declaring IFC4 still runs
       against IFC4X3_ADD2 models. This isolates applicability/requirement semantics.
  vf1  sample models, should_filter_version=True — as a deployed checker behaves: a spec whose
       ifcVersion excludes the model's schema_identifier applies to nothing.
ifcVersion problems are reported separately either way (XSD validity, bad_ifcversion).
"""
from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path

import ifcopenshell
from lxml import etree
from ifctester import ids as idsmod, reporter

from eval import witness
from eval.common import (TESTSET_DIR, XSD_IFC_VERSIONS, graph_property_types, graph_psets,
                         ifc_only, load_tasks, safe_name)

warnings.filterwarnings("ignore")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TESTSET_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


extract = _load("extract_testset")      # facet_target(): the same flattening the targets came from
harness = _load("harness")              # run(): cross-checked against execute() below

NS_IDS = "http://standards.buildingsmart.org/IDS"
NS_XS = "http://www.w3.org/2001/XMLSchema"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
I = lambda t: f"{{{NS_IDS}}}{t}"
X = lambda t: f"{{{NS_XS}}}{t}"
ALL_VERSIONS = "IFC2X3 IFC4 IFC4X3_ADD2"
BOUNDS = {"minInclusive", "maxInclusive", "minExclusive", "maxExclusive"}
_RESTR_SPLIT = re.compile(r",(?=(?:enumeration|pattern|minInclusive|maxInclusive|minExclusive|maxExclusive|"
                          r"length|minLength|maxLength|totalDigits|fractionDigits)=)")
UPPER_FIELDS = {("entity", "name"), ("entity", "predefinedType"), ("partOf", "entity")}


# =========================================================================== canonical facets
def restriction_members(s: str) -> list[tuple[str, str]]:
    body = s[len("RESTRICTION("):-1]
    return [tuple(m.split("=", 1)) for m in _RESTR_SPLIT.split(body) if m] if body else []


def canon_value(kind: str, field: str, v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    up = (kind, field) in UPPER_FIELDS
    if v.startswith("RESTRICTION("):
        mem = sorted((k, (x.strip().upper() if up else x.strip())) for k, x in restriction_members(v))
        return "RESTRICTION(" + ",".join(f"{k}={x}" for k, x in mem) + ")"
    return v.upper() if up else v


def canon(f: dict) -> tuple:
    """Canonical, hashable form of a target-shaped facet dict. `uri`/`instructions` ignored."""
    kind = f["facet"]
    out = [("facet", kind)]
    for fld in extract.FIELDS.get(kind, ()):
        out.append((fld, canon_value(kind, fld, f.get(fld))))
    out.append(("dataType", (f.get("dataType") or "").strip().upper() or None))
    if kind != "entity":                       # entity-in-requirements has no cardinality
        out.append(("cardinality", (f.get("cardinality") or "required").strip().lower()))
    return tuple(out)


def loose_key(f: dict) -> tuple:
    """Identity of a requirement ignoring value/dataType/cardinality — for the error taxonomy."""
    kind = f["facet"]
    if kind == "property":
        return (kind, (f.get("propertySet") or "").strip(), (f.get("baseName") or "").strip())
    if kind == "attribute":
        return (kind, (f.get("name") or "").strip())
    if kind == "classification":
        return (kind, (f.get("system") or "").strip())
    if kind == "entity":
        return (kind, canon_value("entity", "name", f.get("name")))
    if kind == "partOf":
        return (kind, canon_value("partOf", "entity", f.get("entity")))
    return (kind,)


def children(node):
    return [c for c in node if isinstance(c.tag, str)]       # skip comments / PIs


def parse_candidate(path: Path) -> dict:
    """Flatten a generated IDS with the same facet_target() used to build the targets."""
    tree = etree.parse(str(path))
    specs = tree.findall(".//" + I("specification"))
    reqs, apps, versions = [], [], []
    for sp in specs:
        versions.append(sp.get("ifcVersion") or "")
        app = sp.find(I("applicability"))
        ent = app.find(I("entity")) if app is not None else None
        apps.append(extract.facet_target(ent) if ent is not None else {"facet": "entity"})
        req = sp.find(I("requirements"))
        if req is not None:
            reqs += [extract.facet_target(c) for c in children(req)]
    return {"n_specs": len(specs), "requirements": reqs, "applicability": apps, "versions": versions}


def relax(item: dict, ann: list) -> dict:
    """Drop what the request cannot determine: unmentioned requirements go, and value
    constraints nobody could recover are removed while the requirement itself stays.
    `scope=value_extend` goes the other way: the request explicitly permits values the
    reference enumeration lacks, so they are added (`add`: list of values)."""
    drop = {a["facet_index"] for a in ann if a["scope"] == "facet"}
    devalue = {a["facet_index"] for a in ann if a["scope"] == "value"}
    extend = {a["facet_index"]: a["add"] for a in ann if a["scope"] == "value_extend"}
    target = []
    for i, f in enumerate(item["target"]):
        if i in drop:
            continue
        g = dict(f)
        if i in devalue:
            g.pop("value", None)
        elif i in extend and (g.get("value") or "").startswith("RESTRICTION("):
            members = restriction_members(g["value"])
            have = {v for k, v in members if k == "enumeration"}
            members += [("enumeration", v) for v in extend[i] if v not in have]
            g["value"] = "RESTRICTION(" + ",".join(f"{k}={v}" for k, v in members) + ")"
        target.append(g)
    return {**item, "target": target}


def load_annotations(path: Path) -> dict:
    out: dict = {}
    if path.exists():
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            out.setdefault(r["id"], []).append(r)
    return out


def load_extras(path: Path) -> dict:
    """Labels for generated requirements the reference lacks (eval/annotations/extras.jsonl).
    Returns {item id: set of loose keys labelled faithful}."""
    out: dict = {}
    if path.exists():
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r["label"] == "faithful":
                out.setdefault(r["id"], set()).add(tuple(r["key"]))
    return out


def excuse(cand_path: Path, faithful: set, out_path: Path) -> tuple[dict, Path, int]:
    """Mirror image of relax(): drop generated requirements that the request supports but the
    reference never encoded. Writes the trimmed candidate next to the reference variants and
    returns (parsed trimmed candidate, its path, number of facets removed)."""
    tree = etree.parse(str(cand_path))
    removed = 0
    for req in tree.findall(".//" + I("requirements")):
        for c in children(req):
            if loose_key(extract.facet_target(c)) in faithful:
                req.remove(c)
                removed += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(out_path), xml_declaration=True, encoding="UTF-8", standalone=True)
    return parse_candidate(out_path), out_path, removed


def dt_now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else (1.0 if not fn else 0.0)
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def multiset_match(ref: list, cand: list):
    rc, cc = Counter(ref), Counter(cand)
    tp = sum((rc & cc).values())
    return tp, sum(cc.values()) - tp, sum(rc.values()) - tp



# =========================================================================== graded metrics
def verdicts(labels: dict, ex: dict) -> dict:
    """{label: 'pass'|'fail'|'n/a'} for one specification over the test objects."""
    out = {}
    for guid, label in labels.items():
        if guid not in ex["applicable"]:
            out[label] = "n/a"
        else:
            out[label] = "fail" if guid in ex["failed"] else "pass"
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def graded(ref_v: dict, cand_v: dict, side: str | None = None) -> dict:
    """S1/S2/S3 over labelled test objects.

    S1  identical verdict on every object (the strict, all-or-nothing measure).
    S2  fraction of objects both specifications judge the same way.
    S3  decomposed by what each object was built to test:
        enforce       — objects violating exactly one reference requirement that the
                        reference rejects: does the candidate reject them too?
        false_reject  — objects the reference accepts: does the candidate wrongly reject?
        app_out       — objects the reference ignores: does the candidate ignore them?
        app_in        — objects in the reference's scope: are they in the candidate's scope?
    """
    keys = [k for k in ref_v if side is None or k.startswith(side + ":")]
    if not keys:
        return {}
    same = [ref_v[k] == cand_v.get(k, "n/a") for k in keys]
    per_req: dict[str, list] = {}
    false_rej, app_out, app_in = [], [], []
    for k in keys:
        r, c = ref_v[k], cand_v.get(k, "n/a")
        kind = k.split(":")[1] if ":" in k else k
        if kind in ("missing", "badvalue", "badtype", "present") and r == "fail":
            per_req.setdefault(k.split(":")[2] if len(k.split(":")) > 2 else kind, []).append(c == "fail")
        if r == "pass":
            false_rej.append(c != "pass")
        if r == "n/a":
            app_out.append(c == "n/a")
        else:
            app_in.append(c != "n/a")
    return {
        "s1": int(all(same)), "s2": sum(same) / len(same), "n_objects": len(keys),
        "enforce": _mean([_mean(v) for v in per_req.values()]),
        "n_enforce_reqs": len(per_req),
        "false_reject": _mean(false_rej), "n_conforming": len(false_rej),
        "app_out": _mean(app_out), "n_out_of_scope": len(app_out),
        "app_in": _mean(app_in), "n_in_scope": len(app_in),
    }


def length_band(n: int) -> str:
    return "<=3" if n <= 3 else ("4-9" if n <= 9 else ">=10")


# =========================================================================== reference IDS
def _value(parent, tag, v: str):
    w = etree.SubElement(parent, I(tag))
    if v.startswith("RESTRICTION("):
        mem = restriction_members(v)
        base = "xs:double" if any(k in BOUNDS for k, _ in mem) else "xs:string"
        r = etree.SubElement(w, X("restriction"), base=base)
        for k, x in mem:
            etree.SubElement(r, X(k), value=x)
    else:
        etree.SubElement(w, I("simpleValue")).text = v


def _facet(parent, f: dict):
    kind = f["facet"]
    el = etree.SubElement(parent, I(kind))
    for a in ("dataType", "cardinality", "uri"):
        if f.get(a):
            el.set(a, f[a])
    for fld in extract.FIELDS.get(kind, ()):
        if f.get(fld) is not None:
            if kind == "partOf":                     # partOf wraps an entity facet
                _facet(el, {"facet": "entity", "name": f[fld]})
            else:
                _value(el, fld, f[fld])
    return el


def build_reference(item: dict) -> bytes:
    """Reference IDS = task applicability (entity/predefinedType) + target requirement facets.
    ifcVersion lists all three versions so the reference itself is never version-filtered."""
    root = etree.Element(I("ids"), nsmap={"ids": NS_IDS, "xs": NS_XS, "xsi": NS_XSI})
    root.set(f"{{{NS_XSI}}}schemaLocation", f"{NS_IDS} http://standards.buildingsmart.org/IDS/1.0/ids.xsd")
    info = etree.SubElement(root, I("info"))
    etree.SubElement(info, I("title")).text = f"reference {item['id']}"
    specs = etree.SubElement(root, I("specifications"))
    sp = etree.SubElement(specs, I("specification"), name=item.get("spec_name") or item["id"], ifcVersion=ALL_VERSIONS)
    app = etree.SubElement(sp, I("applicability"), minOccurs="0", maxOccurs="unbounded")
    a = item["applicability"]
    ent = etree.SubElement(app, I("entity"))
    _value(ent, "name", a["entity"])
    if a.get("predefinedType"):
        _value(ent, "predefinedType", a["predefinedType"])
    req = etree.SubElement(sp, I("requirements"))
    for f in item["target"]:
        _facet(req, f)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# =========================================================================== XSD
def xsd_check(path: Path) -> tuple[bool, str]:
    from aec_kg.ids.validator import validate_ids_xml
    ok, errs = validate_ids_xml(path.read_text(encoding="utf-8"), strict=True)
    return ok, "; ".join(errs)[:500]


# =========================================================================== execution
def execute(ids_path: Path, model, filter_version: bool) -> dict:
    """harness.run() with a version-filter switch and failure reasons harvested.
    Specs are unioned: an element failing any applicable spec fails."""
    specs = idsmod.open(str(ids_path), validate=True)
    specs.validate(model, should_filter_version=filter_version)
    r = reporter.Json(specs)
    r.report()
    data = json.loads(r.to_string())
    app, passed, failed, reasons = set(), set(), set(), []
    for sp in data.get("specifications", []):
        if sp.get("is_skipped"):
            continue
        app |= {e["global_id"] for e in sp.get("applicable_entities", []) if e.get("global_id")}
        for req in sp.get("requirements", []):
            passed |= {e["global_id"] for e in (req.get("passed_entities") or []) if e.get("global_id")}
            for e in req.get("failed_entities") or []:
                if e.get("global_id"):
                    failed.add(e["global_id"])
                    reasons.append(f"{req.get('facet_type')}:{req.get('label')}: {e.get('reason')}")
    passed -= failed
    return {"applicable": app, "passed": passed, "failed": failed, "reasons": reasons}


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)     # undefined when both raters are constant


def compare(ref: dict, cand: dict) -> dict:
    A, B = ref["applicable"], cand["applicable"]
    inter = A & B
    rv = [g in ref["passed"] for g in sorted(inter)]
    cv = [g in cand["passed"] for g in sorted(inter)]
    union = A | B
    return {
        "n_ref_app": len(A), "n_cand_app": len(B), "n_inter": len(inter),
        "n_ref_pass": len(ref["passed"]), "n_ref_fail": len(ref["failed"]),
        "n_cand_pass": len(cand["passed"]), "n_cand_fail": len(cand["failed"]),
        "app_jaccard": len(inter) / len(union) if union else 1.0,
        "verdict_acc": (sum(x == y for x, y in zip(rv, cv)) / len(inter)) if inter else None,
        "verdict_kappa": cohen_kappa(rv, cv),
        "outcome_equiv": int(ref["passed"] == cand["passed"] and ref["failed"] == cand["failed"]),
        "over_applicable": len(B - A), "under_applicable": len(A - B),
        "over_strict": sum(1 for x, y in zip(rv, cv) if x and not y),     # ref pass, cand fail
        "under_strict": sum(1 for x, y in zip(rv, cv) if y and not x),    # ref fail, cand pass
    }


def direction(c: dict) -> str:
    if c["outcome_equiv"]:
        return "equivalent"
    parts = [k for k in ("over_applicable", "under_applicable", "over_strict", "under_strict") if c[k]]
    return "+".join(parts) or "other"


# =========================================================================== graph snapshot
# =========================================================================== error taxonomy
def taxonomy(item: dict, cand: dict | None, psets: dict | None, ext: dict | None) -> dict:
    e = Counter()
    if cand is None:
        e["no_file"] = 1
        return dict(e)
    tgt = {loose_key(f): f for f in item["target"]}
    got = {loose_key(f): f for f in cand["requirements"]}
    for k in set(tgt) & set(got):
        t, g = tgt[k], got[k]
        if (t.get("dataType") or "").upper() != (g.get("dataType") or "").upper():
            e["wrong_datatype"] += 1
        if (t.get("cardinality") or "required") != (g.get("cardinality") or "required"):
            e["wrong_cardinality"] += 1
        if canon_value(t["facet"], "value", t.get("value")) != canon_value(g["facet"], "value", g.get("value")):
            e["wrong_value"] += 1
    tgt_by_base = {f.get("baseName"): f for f in item["target"] if f["facet"] == "property"}
    for k in set(got) - set(tgt):
        g = got[k]
        if g["facet"] == "property":
            ps = g.get("propertySet") or ""
            if psets is not None and ps not in psets:
                e["hallucinated_pset"] += 1
            if g.get("baseName") in tgt_by_base and tgt_by_base[g["baseName"]].get("propertySet") != ps:
                e["wrong_pset"] += 1
                continue                              # a relocated property is not also "extra"
        e["extra_requirement"] += 1
    got_bases = {g.get("baseName") for g in cand["requirements"] if g["facet"] == "property"}
    for k in set(tgt) - set(got):
        t = tgt[k]
        if t["facet"] == "property" and t.get("baseName") in got_bases:
            continue                                  # counted as wrong_pset
        e["missing_requirement"] += 1
    for g in cand["requirements"] + cand["applicability"]:
        vals = [g.get(k) for k in ("value", "name", "predefinedType", "propertySet", "baseName")]
        e["empty_restriction"] += sum(v == "RESTRICTION()" for v in vals)     # constraint silently dropped
        e["placeholder_value"] += int(str(g.get("value", "")).strip().lower() in PLACEHOLDERS)
    for g in cand["requirements"]:
        dt_ = (g.get("dataType") or "").strip()
        e["invalid_datatype"] += int(bool(dt_) and not _is_ifc_type(dt_))
    if not all("IFC4X3_ADD2" in v.split() for v in cand["versions"] if v):
        e["ifcversion_excludes_model"] += 1      # a version-filtering checker applies it to nothing
    bad = [v for v in " ".join(cand["versions"]).split() if v not in XSD_IFC_VERSIONS]
    if bad:
        e["bad_ifcversion"] += 1
    if ext is not None:
        if ext["over_applicable"] and not ext["under_applicable"]:
            e["applicability_too_broad"] += 1
        elif ext["under_applicable"] and not ext["over_applicable"]:
            e["applicability_too_narrow"] += 1
        elif ext["under_applicable"] and ext["over_applicable"]:
            e["applicability_disjoint"] += 1
    return dict(e)


_IFC_SCHEMA = ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC4X3_ADD2")


def _is_ifc_type(name: str) -> bool:
    """dataType names a real IFC4X3_ADD2 type (the IDS XSD does not check this)."""
    try:
        _IFC_SCHEMA.declaration_by_name(name)
        return True
    except Exception:
        return False


PLACEHOLDERS = {"required", "mandatory", "any", "*", "present", "exists", "not empty", "notempty", "yes"}
def datatype_provenance(cand: dict, ptypes: dict | None) -> dict:
    """Where did each generated dataType come from? The fix only works if the model copies
    the graph's ifc_type, so count that explicitly rather than inferring it from accuracy."""
    out = Counter()
    if cand is None or ptypes is None:
        return {}
    for f in cand["requirements"]:
        if f["facet"] != "property":
            continue
        dt = (f.get("dataType") or "").upper()
        ps, bn = f.get("propertySet") or "", f.get("baseName") or ""
        known = (ptypes.get(ps) or {}).get(bn)
        if not dt:
            out["dt_omitted"] += 1
        elif known and known[0] and dt == known[0].upper():
            out["dt_from_graph"] += 1
            out[f"dt_src_{known[1]}"] += 1
        elif known and not known[0]:
            out["dt_model_choice_no_graph_type"] += 1
        else:
            out["dt_model_choice"] += 1
    return dict(out)


ERROR_COLS = ["no_file", "wrong_datatype", "hallucinated_pset", "wrong_pset", "missing_requirement",
              "extra_requirement", "applicability_too_broad", "applicability_too_narrow",
              "applicability_disjoint", "wrong_cardinality", "wrong_value", "bad_ifcversion",
              "empty_restriction", "placeholder_value", "invalid_datatype", "ifcversion_excludes_model"]
FACET_KINDS = ["property", "attribute", "classification", "material", "partOf", "entity"]


# =========================================================================== main
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("tasks")
    ap.add_argument("models_dir")
    ap.add_argument("--out", help="write scores/reference/witness here instead of into run_dir "
                                 "(use this to score a frozen run without touching it)")
    ap.add_argument("--relaxed", action="store_true",
                    help="score against the determined-only reference (eval/annotations/determinacy.jsonl)")
    ap.add_argument("--annotations", default="eval/annotations/determinacy.jsonl")
    ap.add_argument("--probe", action="store_true",
                    help="add test objects from the symmetric difference of differing value lists "
                         "(writes scores*_probe.csv; the standard scoring is left untouched)")
    ap.add_argument("--excuse-extras", metavar="PATH", nargs="?", const="eval/annotations/extras.jsonl",
                    help="remove generated requirements labelled faithful-to-request in PATH from the "
                         "candidate before scoring (writes scores*_excused.csv)")
    ap.add_argument("--tag", default="", help="suffix for the output files, so annotation variants "
                                             "do not overwrite each other (e.g. --tag _passA)")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])
    run_dir, tasks_path, models_dir = Path(args.run_dir), Path(args.tasks), Path(args.models_dir)
    out_dir = Path(args.out) if args.out else run_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = {t["id"]: t for t in load_tasks(tasks_path)}
    suffix = ""
    if args.relaxed:
        ann = load_annotations(Path(args.annotations))
        if not ann:
            sys.exit(f"no annotations at {args.annotations}; run python -m eval.determinacy first")
        n_before = sum(len(t["target"]) for t in tasks.values())
        tasks = {i: (relax(t, ann[i]) if i in ann else t) for i, t in tasks.items()}
        n_after = sum(len(t["target"]) for t in tasks.values())
        suffix = "_relaxed" + args.tag
        print(f"determined-only reference: {n_before - n_after} requirements dropped, "
              f"{sum(1 for v in ann.values() for a in v if a['scope'] == 'value')} value constraints removed")
    faithful = {}
    if args.excuse_extras:
        faithful = load_extras(Path(args.excuse_extras))
        if not faithful:
            sys.exit(f"no faithful-extra labels at {args.excuse_extras}")
        suffix += "_excused"
        print(f"faithful extras excused: {sum(len(v) for v in faithful.values())} (item, requirement) labels "
              f"on {len(faithful)} items")
    log = {}
    if (run_dir / "log.jsonl").exists():
        for line in open(run_dir / "log.jsonl", encoding="utf-8"):
            r = json.loads(line)
            log[r["id"]] = r                          # last attempt wins
    if args.probe:
        suffix += "_probe"
    gen_dir, ref_dir = run_dir / "generated", out_dir / ("reference" + suffix)
    ref_dir.mkdir(exist_ok=True)
    models = {}
    for p in sorted(models_dir.glob("*.ifc")):
        m = ifcopenshell.open(str(p))
        models[p.stem] = m
    print(f"{len(models)} models: " + ", ".join(f"{k} ({m.schema_identifier})" for k, m in models.items()))
    psets = graph_psets(out_dir) if (out_dir / "graph_psets.json").exists() else graph_psets(run_dir)
    ptypes = graph_property_types(out_dir)

    rows, pair_rows, cross_checked = [], [], 0
    not_generated = 0
    for iid, item in tasks.items():
        name = safe_name(iid)
        cand_path, fail_path = gen_dir / f"{name}.ids", gen_dir / f"{name}.fail.json"
        if not cand_path.exists() and not fail_path.exists():
            not_generated += 1
            continue
        ref_path = ref_dir / f"{name}.ids"
        ref_path.write_bytes(build_reference(item))
        ref_ok, ref_err = xsd_check(ref_path)

        row = {"id": iid, "source": item["source"], "leak": int(bool(item.get("any_leak"))),
               "ifc_only": (int(ifc_only(item, psets)) if psets is not None else None),
               "n_target": len(item["target"]), "status": "ok" if cand_path.exists() else "no_file",
               "ref_xsd_valid": int(ref_ok), "ref_xsd_error": ref_err}
        L = log.get(iid, {})
        row.update({k: L.get(k) for k in ("wall_ms", "cost_usd", "input_tokens", "output_tokens")})
        row["n_tool_calls"] = len(L.get("tool_calls", []))
        row["generate_ids_attempts"] = (L.get("retries") or {}).get("generate_ids_attempts")

        # ---------------- A. intensional
        cand = parse_candidate(cand_path) if cand_path.exists() else None
        row["n_excused"] = 0
        if cand is not None and iid in faithful:
            cand, cand_path, row["n_excused"] = excuse(
                cand_path, faithful[iid], out_dir / ("candidate" + suffix) / f"{name}.ids")
        ref_c = [canon(f) for f in item["target"]]
        cand_c = [canon(f) for f in cand["requirements"]] if cand else []
        tp, fp, fn = multiset_match(ref_c, cand_c)
        p, r, f1 = prf(tp, fp, fn) if cand else (0.0, 0.0, 0.0)
        row.update({"facet_tp": tp, "facet_fp": fp, "facet_fn": fn, "facet_p": p, "facet_r": r, "facet_f1": f1})
        ltp, lfp, lfn = multiset_match([loose_key(f) for f in item["target"]],
                                       [loose_key(f) for f in cand["requirements"]] if cand else [])
        row["loose_f1"] = prf(ltp, lfp, lfn)[2] if cand else 0.0
        for k in FACET_KINDS:
            row[f"{k}_tp"], row[f"{k}_fp"], row[f"{k}_fn"] = multiset_match(
                [c for c in ref_c if c[0][1] == k], [c for c in cand_c if c[0][1] == k])
        if cand:
            ref_app = canon({"facet": "entity", "name": item["applicability"]["entity"],
                             "predefinedType": item["applicability"].get("predefinedType")})
            row["n_specs"] = cand["n_specs"]
            row["app_match"] = int(any(canon(a) == ref_app for a in cand["applicability"]))
            row["ifc_version"] = "|".join(cand["versions"])
            row["ifcversion_xsd_ok"] = int(all(v in XSD_IFC_VERSIONS for v in " ".join(cand["versions"]).split())
                                           and all(cand["versions"]))
            row["ifcversion_covers_models"] = int(all("IFC4X3_ADD2" in v.split() for v in cand["versions"]))
            ok, err = xsd_check(cand_path)
            row["xsd_valid"], row["xsd_error"] = int(ok), err

        # ---------------- B. extensional
        for vf in (0, 1):
            pooled = {"ref": {"applicable": set(), "passed": set(), "failed": set()},
                      "cand": {"applicable": set(), "passed": set(), "failed": set()}}
            skipped = used = 0
            exec_err = ""
            reasons = Counter()
            for mname, model in models.items():
                ref_x = execute(ref_path, model, bool(vf))
                if vf and cross_checked < 25:            # our executor must agree with harness.run
                    h = harness.run(str(ref_path), model)
                    hu = {k: set().union(*(s[k] for s in h)) for k in ("applicable", "passed", "failed")} if h is not None else None
                    assert hu is not None and all(hu[k] == ref_x[k] for k in hu), f"executor != harness on {iid}/{mname}"
                    cross_checked += 1
                if not ref_x["applicable"]:
                    skipped += 1
                    continue
                used += 1
                if cand is None or not row.get("xsd_valid"):
                    cand_x = {"applicable": set(), "passed": set(), "failed": set(), "reasons": []}
                    exec_err = exec_err or ("no_file" if cand is None else "xsd_invalid")
                else:
                    try:
                        cand_x = execute(cand_path, model, bool(vf))
                    except Exception as e:
                        cand_x = {"applicable": set(), "passed": set(), "failed": set(), "reasons": []}
                        exec_err = exec_err or f"{type(e).__name__}: {e}"[:200]
                reasons.update(set(cand_x["reasons"]))
                pr = compare(ref_x, cand_x)
                pair_rows.append({"id": iid, "model": mname, "vf": vf, "leak": row["leak"], **pr,
                                  "direction": direction(pr)})
                for side, x in (("ref", ref_x), ("cand", cand_x)):
                    for k in ("applicable", "passed", "failed"):
                        pooled[side][k] |= {(mname, g) for g in x[k]}
            pre = f"vf{vf}_"
            row[pre + "models_used"], row[pre + "models_skipped"] = used, skipped
            row[pre + "exec_error"] = exec_err
            if used:
                c = compare(pooled["ref"], pooled["cand"])
                row.update({pre + k: v for k, v in c.items()})
                row[pre + "direction"] = direction(c)
                if vf == 0:
                    row["cand_fail_reasons"] = " || ".join(f"{n}x {r}" for r, n in reasons.most_common(4))[:600]
            else:
                row[pre + "outcome_equiv"] = None

        # ---------------- B'. graded, symmetric test models (eval/witness.py)
        wit = witness.build(item, out_dir / ("witness" + suffix) / f"{name}.ifc", candidate=cand,
                            probe=args.probe)
        row["wit_unsupported"] = " | ".join(wit["unsupported"])[:400]
        row["wit_candidate_note"] = wit.get("candidate_note")
        row["wit_sides"] = json.dumps(wit.get("sides", {}))
        if wit["path"]:
            wm = ifcopenshell.open(wit["path"])
            ref_w = execute(ref_path, wm, False)
            probs = witness.verify(wit["labels"], ref_w, item["target"])
            row["wit_n_elements"], row["wit_verified"] = len(wit["labels"]), int(not probs)
            row["wit_problems"] = " | ".join(probs)[:400]
            cand_w, err = {"applicable": set(), "passed": set(), "failed": set(), "reasons": []}, ""
            if cand is None or not row.get("xsd_valid"):
                err = "no_file" if cand is None else "xsd_invalid"
            else:
                try:
                    cand_w = execute(cand_path, wm, False)
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"[:200]
            row["wit_exec_error"] = err
            ref_v, cand_v = verdicts(wit["labels"], ref_w), verdicts(wit["labels"], cand_w)
            if probs:                                 # the model can't be trusted for this item
                row["wit_outcome_equiv"], row["wit_direction"] = None, "witness_unverified"
            elif ref_w["applicable"]:
                c = compare(ref_w, cand_w)
                row.update({"wit_" + k: v for k, v in c.items()})
                row["wit_direction"] = direction(c)
                row["wit_diverging"] = " ".join(sorted(
                    lab for lab in ref_v if ref_v[lab] != cand_v.get(lab, "n/a")))[:800]
                for tag, sd in (("", None), ("_ref", "ref"), ("_cand", "cand")):
                    for k, v in graded(ref_v, cand_v, sd).items():
                        row[f"wit_{k}{tag}"] = v
                row["wit_outcome_equiv"] = row.get("wit_s1")     # S1 is the v4 headline measure
                pair_rows.append({"id": iid, "model": "witness", "vf": 0, "leak": row["leak"], **c,
                                  "direction": direction(c)})
            else:
                row["wit_outcome_equiv"] = None
        else:
            row["wit_outcome_equiv"] = None
        row["band"] = length_band(len(item["target"]))
        row["names_correct"] = int(row.get("loose_f1") == 1.0)

        src = "wit" if row.get("wit_outcome_equiv") is not None else "vf0"
        ext = ({"over_applicable": row.get(f"{src}_over_applicable"),
                "under_applicable": row.get(f"{src}_under_applicable")}
               if row.get(f"{src}_outcome_equiv") is not None else None)
        row.update(datatype_provenance(cand, ptypes))
        tax = taxonomy(item, cand, psets, ext)
        row.update({f"err_{k}": tax.get(k, 0) for k in ERROR_COLS})
        if psets is not None:
            row["ref_psets_not_in_graph"] = sum(1 for f in item["target"] if f["facet"] == "property"
                                                and f.get("propertySet") not in psets)
        rows.append(row)
        print(f"  {iid[:60]:<60} F1={f1:.2f}  equiv(wit)={row.get('wit_outcome_equiv')}  equiv(vf0)={row.get('vf0_outcome_equiv')}  "
              f"equiv(vf1)={row.get('vf1_outcome_equiv')}  skipped={row['vf0_models_skipped']}/{len(models)}")

    cols = []
    for r_ in rows:
        cols += [k for k in r_ if k not in cols]
    with open(out_dir / f"scores{suffix}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    if pair_rows:
        with open(out_dir / f"pairs{suffix}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(pair_rows[0]))
            w.writeheader()
            w.writerows(pair_rows)
    print(f"\nscored {len(rows)} items ({not_generated} task items not generated yet); "
          f"executor cross-checked against harness.run on {cross_checked} (item, model) pairs")
    if out_dir != run_dir:                        # remember where the generated files came from
        (out_dir / "score_meta.json").write_text(json.dumps(
            {"source_run": str(run_dir), "scored": dt_now()}, indent=1))
    print(f"-> {out_dir / f'scores{suffix}.csv'}")


if __name__ == "__main__":
    main()
