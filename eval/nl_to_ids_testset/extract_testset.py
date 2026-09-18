"""Build a natural-language -> IDS test set from real, published reference specifications.

Two framings are emitted:

  spec_tasks.jsonl   one item per SPECIFICATION. prompt = the entity plus every
                     requirement description in that spec; target = the whole spec.
                     This is the realistic authoring task, and it is where the
                     many-facet references live.

  facet_tasks.jsonl  one item per REQUIREMENT. prompt = that one description;
                     target = that one facet. A precise diagnostic of schema lookup.

`leak` is set when the description text contains the property-set or property name
it is supposed to elicit. Filter or hold those out — they turn the task into copying.

usage:  python extract_testset.py <file_or_dir_of_ids> [more ...]
"""
from __future__ import annotations
import glob, json, os, re, sys
from lxml import etree

NS = "http://standards.buildingsmart.org/IDS"
XS = "http://www.w3.org/2001/XMLSchema"
Q  = lambda t: "{%s}%s" % (NS, t)

def _simple(node, tag):
    c = node.find(Q(tag))
    if c is None: return None
    sv = c.find(Q("simpleValue"))
    if sv is not None and sv.text: return sv.text.strip()
    res = c.find("{%s}restriction" % XS)
    if res is not None:
        bits = [f"{etree.QName(g).localname}={g.get('value')}"
                for g in res if isinstance(g.tag, str)]
        return "RESTRICTION(" + ",".join(bits) + ")"
    return None

FIELDS = {
    "property":       ("propertySet", "baseName", "value"),
    "attribute":      ("name", "value"),
    "classification": ("system", "value"),
    "material":       ("value",),
    "partOf":         ("entity",),
    "entity":         ("name", "predefinedType"),
}

def facet_target(fac) -> dict:
    kind = etree.QName(fac).localname
    out = {"facet": kind}
    for f in FIELDS.get(kind, ()):
        v = _simple(fac, f)
        if v is not None: out[f] = v
    for a in ("dataType", "cardinality", "uri"):
        if fac.get(a): out[a] = fac.get(a)
    return out

def names_in(target: dict) -> list:
    return [str(target[k]) for k in ("propertySet", "baseName", "name", "system")
            if target.get(k) and not str(target[k]).startswith("RESTRICTION(")]

def applicability(spec) -> dict:
    app = spec.find(Q("applicability"))
    if app is None: return {}
    ent = app.find(Q("entity"))
    if ent is None: return {}
    d = {"entity": _simple(ent, "name")}
    pt = _simple(ent, "predefinedType")
    if pt: d["predefinedType"] = pt
    return d

def harvest(path: str):
    tree = etree.parse(path)
    src = os.path.basename(path)
    info = tree.find(".//" + Q("info"))
    title = (info.findtext(Q("title")) or "").strip() if info is not None else ""
    specs, facets = [], []
    for si, spec in enumerate(tree.findall(".//" + Q("specification")), 1):
        app = applicability(spec)
        req = spec.find(Q("requirements"))
        if req is None or not [c for c in req if isinstance(c.tag, str)]: continue
        items = []
        for fi, fac in enumerate([c for c in req if isinstance(c.tag, str)], 1):
            tgt = facet_target(fac)
            text = (fac.get("instructions") or "").strip()
            leak = bool(text) and any(n in text for n in names_in(tgt))
            items.append({"facet_index": fi, "description": text, "target": tgt, "leak": leak})
        described = [i for i in items if i["description"]]
        for i in described:
            facets.append({
                "id": f"{src}#{si}.{i['facet_index']}", "source": src, "ids_title": title,
                "spec_name": spec.get("name"), "applicability": app,
                "prompt": i["description"], "target": i["target"], "leak": i["leak"],
            })
        if described:
            specs.append({
                "id": f"{src}#{si}", "source": src, "ids_title": title,
                "spec_name": spec.get("name"), "applicability": app,
                "n_requirements": len(items), "n_described": len(described),
                "any_leak": any(i["leak"] for i in described),
                "prompt": {"applies_to": app, "requirements": [i["description"] for i in described]},
                "target": [i["target"] for i in items],
            })
    return specs, facets

def main(argv):
    paths = []
    for a in argv or ["."]:
        paths += [a] if a.endswith(".ids") else glob.glob(os.path.join(a, "**", "*.ids"), recursive=True)
    S, F = [], []
    for p in sorted(set(paths)):
        try:
            s, f = harvest(p)
        except Exception as e:
            print(f"  skip {os.path.basename(p)}: {e}"); continue
        if s or f: print(f"  {os.path.basename(p)[:58]:<58} {len(s):>4} specs  {len(f):>4} facets")
        S += s; F += f
    for name, rows in (("spec_tasks.jsonl", S), ("facet_tasks.jsonl", F)):
        with open(name, "w") as fh:
            for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote spec_tasks.jsonl ({len(S)}) and facet_tasks.jsonl ({len(F)})")
    clean = [r for r in F if not r["leak"]]
    multi = [r for r in S if r["n_described"] >= 5]
    print(f"  facet tasks with no leakage: {len(clean)}")
    print(f"  spec tasks with >=5 described requirements: {len(multi)}")

if __name__ == "__main__":
    main(sys.argv[1:])
