"""Gate-1 probe: does extensional (behavioural) IDS agreement discriminate where facet-F1 does not?

Controlled experiment. We take each buildingSMART conformance .ids as a *reference*
specification, apply one realistic LLM-style error to produce a *candidate*, then run
BOTH against the matched .ifc model and compare:
  intensional : facet-level precision/recall/F1   (what the field measures)
  extensional : element-GUID pass/fail partition  (what actually matters)
"""
from __future__ import annotations
import copy, glob, io, json, os, re, warnings
from dataclasses import dataclass
from lxml import etree
import ifcopenshell
from ifctester import ids as idsmod, reporter

warnings.filterwarnings("ignore")
NS = {"ids": "http://standards.buildingsmart.org/IDS", "xs": "http://www.w3.org/2001/XMLSchema"}
I = lambda t: "{%s}%s" % (NS["ids"], t)
X = lambda t: "{%s}%s" % (NS["xs"], t)

# ---------------------------------------------------------------- execution
def run(ids_path: str, model) -> dict | None:
    """Execute an IDS against a loaded model; return per-spec GUID partitions."""
    try:
        specs = idsmod.open(ids_path, validate=False)
        specs.validate(model, should_filter_version=True)
        r = reporter.Json(specs); r.report()
        data = json.loads(r.to_string())
    except Exception as e:
        return None
    out = []
    for sp in data.get("specifications", []):
        if sp.get("is_skipped"):
            continue
        app = {e.get("global_id") for e in sp.get("applicable_entities", []) if e.get("global_id")}
        p, f = set(), set()
        for req in sp.get("requirements", []):
            p |= {e.get("global_id") for e in (req.get("passed_entities") or []) if e.get("global_id")}
            f |= {e.get("global_id") for e in (req.get("failed_entities") or []) if e.get("global_id")}
        p -= f                     # an element failing any requirement fails the spec
        out.append({"applicable": app, "passed": p, "failed": f, "status": sp.get("status")})
    return out

# ---------------------------------------------------------------- facets
def facets(ids_path: str) -> set:
    """Flatten an IDS into a comparable set of facet tuples (the intensional view)."""
    tree = etree.parse(ids_path)
    got = set()
    for si, spec in enumerate(tree.iter(I("specification"))):
        for part in ("applicability", "requirements"):
            node = spec.find(I(part))
            if node is None: continue
            for fac in node:
                kind = etree.QName(fac).localname
                fields = [f"{kind}@{part}"]
                for child in fac:
                    cn = etree.QName(child).localname
                    sv = child.find(I("simpleValue"))
                    if sv is not None:
                        fields.append(f"{cn}={(sv.text or '').strip()}")
                    else:
                        res = child.find(X("restriction"))
                        if res is not None:
                            bits = [f"{etree.QName(g).localname}:{g.get('value')}" for g in res]
                            fields.append(f"{cn}=RESTR({res.get('base')};{','.join(sorted(bits))})")
                for k in ("dataType", "cardinality", "uri"):
                    if fac.get(k): fields.append(f"{k}={fac.get(k)}")
                got.add((si, "|".join(fields)))
    return got

def prf(ref: set, cand: set) -> tuple:
    tp = len(ref & cand); fp = len(cand - ref); fn = len(ref - cand)
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else (1.0 if not ref and not cand else 0.0)
    return p, r, f

# ---------------------------------------------------------------- perturbations
DT = {"IFCLABEL":"IFCTEXT","IFCTEXT":"IFCLABEL","IFCBOOLEAN":"IFCLOGICAL","IFCLOGICAL":"IFCBOOLEAN",
      "IFCREAL":"IFCINTEGER","IFCINTEGER":"IFCREAL","IFCIDENTIFIER":"IFCLABEL",
      "IFCLENGTHMEASURE":"IFCPOSITIVELENGTHMEASURE","IFCPOSITIVELENGTHMEASURE":"IFCLENGTHMEASURE"}

def _sv(parent, tag):
    c = parent.find(I(tag))
    return None if c is None else c.find(I("simpleValue"))

def mutations(tree):
    """Yield (label, mutated_tree). One realistic LLM error each."""
    def fresh(): return copy.deepcopy(tree)

    # 1 wrong dataType on a property facet
    for t in [fresh()]:
        for pr in t.iter(I("property")):
            dt = pr.get("dataType")
            if dt and dt.upper() in DT:
                pr.set("dataType", DT[dt.upper()]); yield "dataType_swap", t; break

    # 2 plausible-but-wrong property set name
    for t in [fresh()]:
        for pr in t.iter(I("property")):
            sv = _sv(pr, "propertySet")
            if sv is not None and sv.text:
                sv.text = sv.text.strip().replace("Common", "ElementCommon") if "Common" in sv.text \
                          else sv.text.strip() + "Common"
                yield "pset_rename", t; break

    # 3 typo in the property base name
    for t in [fresh()]:
        for pr in t.iter(I("property")):
            sv = _sv(pr, "baseName")
            if sv is not None and sv.text and len(sv.text.strip()) > 3:
                s = sv.text.strip(); sv.text = s[0].lower() + s[1:]
                yield "baseName_case", t; break

    # 4 drop predefinedType from applicability -> widens the applicable set
    for t in [fresh()]:
        for ent in t.iter(I("entity")):
            pt = ent.find(I("predefinedType"))
            if pt is not None:
                ent.remove(pt); yield "drop_predefinedType", t; break

    # 5 over-strict restriction: delete one enumeration option
    for t in [fresh()]:
        done = False
        for res in t.iter(X("restriction")):
            enums = [g for g in res if etree.QName(g).localname == "enumeration"]
            if len(enums) > 1:
                res.remove(enums[-1]); done = True; break
        if done: yield "restriction_tighten", t

    # 6 cardinality required -> optional
    for t in [fresh()]:
        for fac in t.iter():
            if fac.get("cardinality") == "required":
                fac.set("cardinality", "optional"); yield "cardinality_relax", t; break

    # 7 entity name broadened to a generic supertype
    for t in [fresh()]:
        spec = t.find(".//" + I("applicability"))
        if spec is not None:
            ent = spec.find(I("entity"))
            if ent is not None:
                sv = _sv(ent, "name")
                if sv is not None and sv.text and sv.text.strip() != "IFCBUILTELEMENT":
                    sv.text = "IFCBUILTELEMENT"; yield "entity_broaden", t

def write(tree, path):
    tree.write(path, xml_declaration=True, encoding="UTF-8")
    return path
