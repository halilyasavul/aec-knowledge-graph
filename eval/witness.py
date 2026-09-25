"""Witness models: small IFC files built from a *reference* specification only.

The sample buildings rarely contain the elements or properties a reference asks for, so a
reference and a wrong candidate both fail everything and look "equivalent". A witness
model is a surface on which the reference's verdicts carry information:

  full            elements that satisfy every reference requirement      -> reference PASS
  altvalue:i:k    full, with the k-th allowed enumeration value for i    -> PASS
  edge:i:bound    full, with i exactly on an inclusive numeric bound     -> PASS
  missing:i       full, minus requirement i                              -> FAIL if i is required
  badvalue:i      requirement i present with a value violating its constraint  -> FAIL
  badtype:i       property i present with a different IFC dataType      -> FAIL
  present:i       a prohibited requirement i supplied                   -> FAIL
  decoy:class     another entity class carrying every property          -> not applicable
  decoy:ptype     same class, another predefined type                    -> not applicable

The candidate never influences the model, so running reference and candidate on it is a
fair differential test. `verify()` checks that the reference behaves as labelled above; a
witness it can't fully verify is still used but flagged.

No geometry, no spatial tree: IDS facets used here don't need them (partOf excepted, which
is flagged as unsupported).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
from ifcopenshell import ifcopenshell_wrapper as W

SCHEMA_NAME = "IFC4X3_ADD2"
S = W.schema_by_name(SCHEMA_NAME)
_NS = uuid.UUID("6f1c0a52-9e37-4a8e-9b1f-6d2c5e0f7a11")
BOUNDS = ("minInclusive", "minExclusive", "maxInclusive", "maxExclusive")
PATTERN_SAMPLES = ["Witness 01", "00 groundfloor", "A1", "Witness", "X", "01", "1", "a", "W-01",
                   "00 Witness", "-01 Witness", "Level 01", "Niveau 01"]
PATTERN_NONMATCH = ["", " ", "!!", "zz zz zz ??", "0", "Witness 01", "a" * 300]


# ------------------------------------------------------------------ restriction parsing
_SPLIT = re.compile(r",(?=(?:enumeration|pattern|minInclusive|maxInclusive|minExclusive|maxExclusive|"
                    r"length|minLength|maxLength|totalDigits|fractionDigits)=)")


def parse(v: str | None) -> dict | None:
    """'RESTRICTION(a=1,enumeration=X,enumeration=Y)' -> {'enumeration': ['X','Y'], 'a': '1'};
    a plain value -> {'simple': v}; None -> None."""
    if v is None:
        return None
    v = v.strip()
    if not v.startswith("RESTRICTION("):
        return {"simple": v}
    out: dict = {}
    body = v[len("RESTRICTION("):-1]
    for m in (_SPLIT.split(body) if body else []):
        k, x = m.split("=", 1)
        if k == "enumeration":
            out.setdefault("enumeration", []).append(x)
        else:
            out[k] = x
    return out


def first(v: str | None) -> str | None:
    """A single concrete name for a name field that may be a restriction."""
    r = parse(v)
    if r is None:
        return None
    if "simple" in r:
        return r["simple"]
    if r.get("enumeration"):
        return r["enumeration"][0]
    if "pattern" in r:
        return sample_pattern(r["pattern"])
    return None


def xsd_match(pattern: str, s: str) -> bool:
    try:
        return re.fullmatch(pattern, s) is not None
    except re.error:
        return False


def sample_pattern(pattern: str) -> str | None:
    for s in PATTERN_SAMPLES:
        if xsd_match(pattern, s):
            return s
    try:
        import rstr
        for _ in range(50):
            s = rstr.xeger(pattern)
            if xsd_match(pattern, s):
                return s
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ IFC type resolution
def resolve(t):
    """Follow named types to ('string'|'real'|'integer'|'number'|'boolean'|'logical'|'binary', None)
    or ('enum', items) or ('list', (kind, lower_bound)) or ('entity'|'select', None)."""
    while True:
        if isinstance(t, W.named_type):
            t = t.declared_type()
        if isinstance(t, W.type_declaration):
            t = t.declared_type()
            continue
        if isinstance(t, W.enumeration_type):
            return "enum", list(t.enumeration_items())
        if isinstance(t, W.select_type):
            return "select", None
        if isinstance(t, W.entity):
            return "entity", None
        if isinstance(t, W.simple_type):
            return t.declared_type(), None
        if isinstance(t, W.aggregation_type):
            inner, _ = resolve(t.type_of_element())
            return "list", (inner, max(t.bound1(), 1))
        return "unknown", None


def type_kind(type_name: str) -> str:
    try:
        return resolve(S.declaration_by_name(type_name))[0]
    except Exception:
        return "unknown"


def cast(kind: str, v):
    if kind in ("real", "number"):
        return float(v)
    if kind == "integer":
        return int(float(v))
    if kind == "boolean":
        return v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1")
    if kind == "logical":
        return v if isinstance(v, bool) else {"true": True, "false": False}.get(str(v).strip().lower(), "UNKNOWN")
    return str(v)


def _safe(fn):
    """Candidate specifications are arbitrary: an unrepresentable value means 'no such test
    object', never a crash."""
    def wrap(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception:
            return None
    return wrap


def ok_value(kind: str, r: dict | None):
    """A value of `kind` satisfying restriction r (None = unconstrained)."""
    if r is None:
        return {"string": "Witness", "real": 1.0, "number": 1.0, "integer": 1,
                "boolean": True, "logical": True}.get(kind, "Witness")
    if "simple" in r:
        return cast(kind, r["simple"])
    if r.get("enumeration"):
        return cast(kind, r["enumeration"][0])
    if any(b in r for b in BOUNDS):
        lo = float(r.get("minInclusive", r.get("minExclusive", "nan")))
        hi = float(r.get("maxInclusive", r.get("maxExclusive", "nan")))
        if lo == lo and hi == hi:
            v = (lo + hi) / 2
        elif lo == lo:
            v = lo + 1
        else:
            v = hi - 1
        return cast(kind, v if kind != "integer" else (int(v) if v == int(v) else int(v) + (1 if lo == lo else 0)))
    if "pattern" in r:
        s = sample_pattern(r["pattern"])
        return None if s is None else cast(kind, s)
    if any(k in r for k in ("length", "minLength", "maxLength")):
        n = int(r.get("length", r.get("minLength", min(int(r.get("maxLength", 7)), 7))))
        return "W" * max(n, 1) if kind == "string" else cast(kind, 1)
    return ok_value(kind, None)


def bad_value(kind: str, r: dict | None):
    """A value of `kind` violating r, or None when r has no violable constraint."""
    if r is None:
        return None
    if "simple" in r:
        v = cast(kind, r["simple"])
        if kind in ("boolean", "logical"):
            return not v if isinstance(v, bool) else False
        if kind in ("real", "number", "integer"):
            return cast(kind, v + 1)
        return str(v) + "_x"
    if r.get("enumeration"):
        if kind in ("real", "number", "integer"):
            return cast(kind, max(float(x) for x in r["enumeration"]) + 1)
        if kind in ("boolean", "logical"):
            vals = {cast(kind, x) for x in r["enumeration"]}
            rest = [x for x in (True, False) if x not in vals]
            return rest[0] if rest else None
        return "NOT_IN_ENUMERATION"
    if any(b in r for b in BOUNDS):
        if "minExclusive" in r:
            v = float(r["minExclusive"])
        elif "minInclusive" in r:
            v = float(r["minInclusive"]) - 1
        elif "maxExclusive" in r:
            v = float(r["maxExclusive"])
        else:
            v = float(r["maxInclusive"]) + 1
        return cast(kind, v)
    if "pattern" in r:
        for s in PATTERN_NONMATCH:
            if s and not xsd_match(r["pattern"], s):
                return cast(kind, s)
        return None
    if "maxLength" in r or "length" in r:
        return "W" * (int(r.get("maxLength", r.get("length"))) + 1)
    if "minLength" in r:
        return "W" * max(int(r["minLength"]) - 1, 0) or None
    return None


ok_value = _safe(ok_value)
bad_value = _safe(bad_value)

ALT_TYPE = {"IFCLABEL": "IFCTEXT", "IFCTEXT": "IFCLABEL", "IFCIDENTIFIER": "IFCLABEL",
            "IFCBOOLEAN": "IFCLOGICAL", "IFCLOGICAL": "IFCBOOLEAN", "IFCREAL": "IFCINTEGER",
            "IFCINTEGER": "IFCREAL", "IFCCOUNTMEASURE": "IFCREAL"}


def alt_type(dt: str) -> str:
    dt = dt.upper()
    if dt in ALT_TYPE:
        return ALT_TYPE[dt]
    k = type_kind(dt)
    return {"real": "IFCREAL", "number": "IFCREAL", "integer": "IFCREAL", "string": "IFCLABEL"}.get(k, "IFCLABEL")


# ------------------------------------------------------------------ model construction
class Builder:
    def __init__(self, item_id: str):
        self.item_id = item_id
        self.f = ifcopenshell.file(schema=SCHEMA_NAME)
        self.labels: dict[str, str] = {}
        self.n = 0
        self.unsupported: list[str] = []
        self.psets: dict = {}
        self._units()

    def guid(self, label: str) -> str:
        self.n += 1
        return ifcopenshell.guid.compress(uuid.uuid5(_NS, f"{self.item_id}|{label}|{self.n}").hex)

    def _units(self):
        f = self.f
        units = [f.create_entity("IfcSIUnit", UnitType=u, Name=n) for u, n in
                 (("LENGTHUNIT", "METRE"), ("AREAUNIT", "SQUARE_METRE"), ("VOLUMEUNIT", "CUBIC_METRE"),
                  ("PLANEANGLEUNIT", "RADIAN"), ("TIMEUNIT", "SECOND"), ("MASSUNIT", "GRAM"))]
        self.project = f.create_entity("IfcProject", GlobalId=self.guid("project"), Name="witness",
                                       UnitsInContext=f.create_entity("IfcUnitAssignment", Units=units))

    def element(self, cls: str, label: str, ptype: str | None):
        f = self.f
        if cls.upper() == "IFCPROJECT" and self.project.GlobalId not in self.labels:
            el = self.project                       # the first project variant is the file's own project
        else:
            el = f.create_entity(S.declaration_by_name(cls).name(), GlobalId=self.guid(label))
        el.Name = f"witness {label}"
        if ptype:
            self.set_ptype(el, ptype)
        assert el.GlobalId not in self.labels, f"element relabelled: {self.labels[el.GlobalId]} -> {label}"
        self.labels[el.GlobalId] = label
        return el

    def set_ptype(self, el, ptype: str):
        decl = S.declaration_by_name(el.is_a())
        names = [a.name() for a in decl.all_attributes()]
        if "PredefinedType" not in names:
            self.unsupported.append(f"{el.is_a()} has no PredefinedType")
            return
        kind, items = resolve(decl.attribute_by_index(decl.attribute_index("PredefinedType")).type_of_attribute())
        if ptype.upper() in (items or []) and ptype.upper() == ptype:
            el.PredefinedType = ptype
        else:                                        # user-defined type: IDS matches ObjectType
            el.PredefinedType = "USERDEFINED"
            if "ObjectType" in names:
                el.ObjectType = ptype

    def attribute(self, el, name: str, value) -> bool:
        try:
            setattr(el, name, value)
            return True
        except Exception as e:
            self.unsupported.append(f"attribute {name}={value!r}: {e}"[:160])
            return False

    def prop(self, el, pset: str, name: str, dtype: str | None, value):
        f = self.f
        dtype = (dtype or ("IFCREAL" if isinstance(value, float) else "IFCINTEGER" if isinstance(value, int)
                           and not isinstance(value, bool) else "IFCBOOLEAN" if isinstance(value, bool)
                           else "IFCLABEL"))
        kind = type_kind(dtype)
        try:
            nominal = f.create_entity(S.declaration_by_name(dtype).name(), cast(kind, value))
        except Exception as e:
            self.unsupported.append(f"property {pset}.{name} {dtype}={value!r}: {e}"[:160])
            return
        p = f.create_entity("IfcPropertySingleValue", Name=name, NominalValue=nominal)
        key = (el.id(), pset)                        # one set per (element, name), as a checker expects
        if key in self.psets:
            ps = self.psets[key]
            ps.HasProperties = list(ps.HasProperties) + [p]
            return
        ps = f.create_entity("IfcPropertySet", GlobalId=self.guid("pset"), Name=pset, HasProperties=[p])
        self.psets[key] = ps
        f.create_entity("IfcRelDefinesByProperties", GlobalId=self.guid("rel"), RelatedObjects=[el],
                        RelatingPropertyDefinition=ps)

    def material(self, el, name: str):
        m = self.f.create_entity("IfcMaterial", Name=name)
        self.f.create_entity("IfcRelAssociatesMaterial", GlobalId=self.guid("mat"), RelatedObjects=[el],
                             RelatingMaterial=m)

    def classification(self, el, system: str, value: str | None):
        f = self.f
        c = f.create_entity("IfcClassification", Name=system)
        ref = f.create_entity("IfcClassificationReference", Identification=value or "W1", ReferencedSource=c)
        f.create_entity("IfcRelAssociatesClassification", GlobalId=self.guid("cls"), RelatedObjects=[el],
                        RelatingClassification=ref)


def _attr_kind(cls: str, name: str):
    decl = S.declaration_by_name(cls)
    try:
        return resolve(decl.attribute_by_index(decl.attribute_index(name)).type_of_attribute())
    except Exception:
        return "missing", None


def apply_facet(b: Builder, el, f: dict, mode: str = "ok", r_override: dict | None = None) -> bool:
    try:
        return _apply_facet(b, el, f, mode, r_override)
    except Exception as e:                           # never let one odd facet kill the run
        b.unsupported.append(f"facet {f.get('facet')} {mode}: {type(e).__name__}: {e}"[:160])
        return False


def _apply_facet(b: Builder, el, f: dict, mode: str = "ok", r_override: dict | None = None) -> bool:
    """Put requirement f on element el. mode: ok | bad (violating value) | badtype. False = couldn't."""
    kind_ = f["facet"]
    r = r_override if r_override is not None else parse(f.get("value"))
    if kind_ == "attribute":
        name = first(f.get("name"))
        k, extra = _attr_kind(el.is_a(), name)
        if k == "enum":
            allowed = [x for x in (r or {}).get("enumeration", extra) if x in extra] or \
                      ([r["simple"]] if r and "simple" in r and r["simple"] in extra else extra)
            pick = [x for x in allowed if x not in ("USERDEFINED", "NOTDEFINED")] or allowed
            if mode == "ok":
                return b.attribute(el, name, pick[0])
            other = [x for x in extra if x not in allowed]
            return bool(other) and b.attribute(el, name, other[0])
        if k == "list":
            inner, n = extra
            return mode == "ok" and b.attribute(el, name, tuple(cast(inner, 1) for _ in range(n)))
        if k in ("entity", "select", "missing", "unknown"):
            b.unsupported.append(f"attribute {name}: type {k}")
            return False
        v = ok_value(k, r) if mode == "ok" else bad_value(k, r)
        return v is not None and b.attribute(el, name, v)
    if kind_ == "property":
        pset, name, dt = first(f.get("propertySet")), first(f.get("baseName")), f.get("dataType")
        if not pset or not name:
            b.unsupported.append(f"property name not concretisable: {f}")
            return False
        k = type_kind(dt) if dt else ("real" if r and any(x in r for x in BOUNDS) else "string")
        if mode == "badtype":
            if not dt:
                return False
            at = alt_type(dt)
            v = ok_value(type_kind(at), None if type_kind(at) != type_kind(dt) else r)
            b.prop(el, pset, name, at, v)
            return True
        v = ok_value(k, r) if mode == "ok" else bad_value(k, r)
        if v is None:
            return False
        b.prop(el, pset, name, dt, v)
        return True
    if kind_ == "material":
        rv = first(f.get("value"))
        if mode == "ok":
            b.material(el, rv or "Witness material")
            return True
        if r and "simple" in r or (r and r.get("enumeration")):
            b.material(el, "NOT_THIS_MATERIAL")
            return True
        return False
    if kind_ == "classification":
        if mode == "ok":
            b.classification(el, first(f.get("system")) or "Witness", first(f.get("value")))
            return True
        return False
    if kind_ == "entity":                            # class is satisfied by the element itself
        pr = parse(f.get("predefinedType"))
        if pr is None:
            return mode == "ok"
        allowed = pr.get("enumeration") or ([pr["simple"]] if "simple" in pr else [])
        k, items = _attr_kind(el.is_a(), "PredefinedType")
        if mode == "ok":
            cur = getattr(el, "PredefinedType", None) if k == "enum" else None
            if cur not in allowed:
                pick = [x for x in allowed if x not in ("USERDEFINED", "NOTDEFINED")] or allowed
                b.set_ptype(el, pick[0])
            return True
        other = [x for x in (items or []) if x not in allowed and x != "USERDEFINED"]
        if not other:
            return False
        b.set_ptype(el, other[0])
        return True
    b.unsupported.append(f"facet {kind_} not supported")
    return False


def _classes(app: dict) -> list[str]:
    r = parse(app["entity"])
    names = r.get("enumeration") or ([r["simple"]] if "simple" in r else [])
    return [n for n in names if _exists(n)]


def _exists(cls: str) -> bool:
    """A concrete IfcRoot subtype: only those carry the GlobalId that verdicts are keyed on."""
    try:
        d = S.declaration_by_name(cls)
    except Exception:
        return False
    if not isinstance(d, W.entity) or d.is_abstract():
        return False
    while d is not None:
        if d.name() == "IfcRoot":
            return True
        d = d.supertype()
    return False


def _ptypes(app: dict) -> list[str]:
    r = parse(app.get("predefinedType"))
    if r is None:
        return []
    return r.get("enumeration") or ([r["simple"]] if "simple" in r else [])


def _loose(f: dict) -> tuple:
    """Requirement identity ignoring values — to find candidate requirements the reference lacks."""
    k = f["facet"]
    if k == "property":
        return (k, first(f.get("propertySet")) or "", first(f.get("baseName")) or "")
    if k == "attribute":
        return (k, first(f.get("name")) or "")
    if k == "entity":
        return (k, (first(f.get("name")) or "").upper())
    return (k, str(f.get("value") or ""))


def _emit(b, app: dict, target: list, side: str, mutate: set | None = None,
          with_decoys: bool = True) -> None:
    """Add one side's objects to the model. Labels are '<side>:<kind>[:index]'.

    mutate: requirement indices to build violating objects for (None = all).
    """
    classes = _classes(app)
    if not classes:
        b.unsupported.append(f"{side}: entity {app.get('entity')!r} not a concrete IfcRoot")
        return
    ptypes = _ptypes(app)
    usable = [p for p in ptypes if p not in ("USERDEFINED", "NOTDEFINED")] or ptypes
    ptype = usable[0] if usable else None
    if len(ptypes) > 1 and "USERDEFINED" in ptypes:
        # ifctester 0.8.5 compares a predefinedType restriction to the string "USERDEFINED" and the
        # enumeration contains it, so it only applies to user-defined elements. Build for the
        # checker as it behaves; reference and candidate run through the same code path.
        ptype = "WitnessUserDefinedType"
    reqs = [f for f in target if (f.get("cardinality") or "required") != "prohibited"]
    prohibited = [f for f in target if f.get("cardinality") == "prohibited"]

    def full(cls, label, pt, skip=None, override=None, decoy=False):
        el = b.element(cls, f"{side}:{label}", pt)
        for i, f in enumerate(reqs):
            if decoy and f["facet"] == "entity":     # keep the decoy's class / predefined type
                continue
            if i == skip:
                if f["facet"] == "attribute" and first(f.get("name")):
                    try:
                        setattr(el, first(f.get("name")), None)
                    except Exception:
                        pass
                continue
            if override and override[0] == i:
                if not apply_facet(b, el, f, override[1], *override[2:]):
                    return None
            else:
                apply_facet(b, el, f, "ok")
        return el

    for cls in classes:                              # one conforming object per allowed class
        full(cls, f"full:{cls.upper()}", ptype)
    cls = classes[0]
    for i, f in enumerate(reqs):
        if mutate is not None and i not in mutate:
            continue
        if f["facet"] != "entity":                   # an element can't lack its own class
            full(cls, f"missing:{i}", ptype, skip=i)
        if parse(f.get("value")) is not None or (f["facet"] == "entity" and f.get("predefinedType") and not ptypes) or \
                (f["facet"] == "attribute" and _attr_kind(cls, first(f.get("name")) or "")[0] == "enum"):
            _try(b, lambda: full(cls, f"badvalue:{i}", ptype, override=(i, "bad")))
        if f["facet"] == "property" and f.get("dataType"):
            _try(b, lambda: full(cls, f"badtype:{i}", ptype, override=(i, "badtype")))
        r = parse(f.get("value")) or {}
        for k, alt in enumerate((r.get("enumeration") or [])[1:30], 1):   # every other allowed value
            _try(b, lambda: full(cls, f"altvalue:{i}:{k}", ptype, override=(i, "ok", {"enumeration": [alt]})))
        for bound in ("minInclusive", "maxInclusive"):                     # inclusive edges pass
            if bound in r:
                _try(b, lambda: full(cls, f"edge:{i}:{bound}", ptype, override=(i, "ok", {"simple": r[bound]})))
    for j, f in enumerate(prohibited):
        el = full(cls, f"present:{j}", ptype)
        if el is not None:
            apply_facet(b, el, f, "ok")
    if not with_decoys:
        return
    decoy_cls = "IFCWALL" if cls.upper() == "IFCBUILDINGELEMENTPROXY" else "IFCBUILDINGELEMENTPROXY"
    if decoy_cls not in [c.upper() for c in classes]:
        full(decoy_cls, "decoy:class", None, decoy=True)
    if ptype:
        kind, items = _attr_kind(cls, "PredefinedType")
        others = [x for x in (items or []) if x not in ptypes and x not in ("USERDEFINED", "NOTDEFINED")]
        full(cls, "decoy:ptype", others[0] if others else "OtherUserDefinedType", decoy=True)


def build(item: dict, out_path: Path, candidate: dict | None = None) -> dict:
    """Write the test model for one item and return {guid: label} plus build notes.

    Objects come from BOTH specifications so neither side is privileged: the reference
    contributes conforming objects, one-requirement violations and out-of-scope decoys;
    the candidate contributes a conforming object of its own plus violations of any
    requirement the reference does not have. Labels carry the side ('ref:' / 'cand:').
    """
    b = Builder(item["id"])
    _emit(b, item["applicability"], item["target"], "ref")
    if not b.labels:
        return {"labels": {}, "unsupported": sorted(set(b.unsupported)) or
                [f"entity {item['applicability'].get('entity')!r} not a concrete IfcRoot in {SCHEMA_NAME}"],
                "path": None}
    cand_note = None
    if candidate:
        ref_keys = {_loose(f) for f in item["target"]}
        cand_reqs = [f for f in candidate["requirements"]
                     if (f.get("cardinality") or "required") != "prohibited"]
        extra = {i for i, f in enumerate(cand_reqs) if _loose(f) not in ref_keys}
        app = candidate["applicability"][0] if candidate.get("applicability") else {}
        cand_app = {"entity": first(app.get("name")) or item["applicability"].get("entity"),
                    "predefinedType": app.get("predefinedType")}
        before = len(b.labels)
        _emit(b, cand_app, candidate["requirements"], "cand", mutate=extra, with_decoys=False)
        if len(b.labels) == before:
            cand_note = "candidate produced no objects (unsatisfiable or unbuildable applicability)"
            b.unsupported.append("cand: " + cand_note)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    b.f.write(str(out_path))
    meta = {"labels": b.labels, "unsupported": sorted(set(b.unsupported)), "path": str(out_path),
            "candidate_note": cand_note,
            "sides": {s: sum(1 for v in b.labels.values() if v.startswith(s + ":")) for s in ("ref", "cand")}}
    out_path.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    return meta


def _try(b: Builder, fn):
    n0 = dict(b.labels)
    el = fn()
    if el is None:                                   # variant couldn't be expressed: forget it
        for g in set(b.labels) - set(n0):
            b.labels.pop(g)
            try:
                b.f.remove(b.f.by_guid(g))
            except Exception:
                pass                                 # already gone (e.g. the reused project)


def expected(label: str, target: list, reqs_opt: dict) -> str:
    """What the reference should do to a reference-derived variant: pass | fail | n/a | either."""
    side, _, rest = label.partition(":")
    if side != "ref":
        return "either"                              # candidate-derived objects are not predictable
    kind, _, idx = rest.partition(":")
    if kind in ("full", "altvalue", "edge"):
        return "pass"
    if kind == "decoy":
        return "n/a"
    if kind == "missing":
        return "either" if reqs_opt.get(int(idx.split(":")[0])) else "fail"
    if kind == "badvalue" or kind == "badtype":
        return "fail"
    if kind == "present":
        return "fail"
    return "either"


def verify(labels: dict, ref_exec: dict, target: list) -> list[str]:
    """Check the reference behaves as labelled on its own witness; return problems."""
    reqs = [f for f in target if (f.get("cardinality") or "required") != "prohibited"]
    opt = {i: (f.get("cardinality") == "optional") for i, f in enumerate(reqs)}
    probs = []
    for g, label in labels.items():
        exp = expected(label, target, opt)
        if exp == "n/a":
            got = "n/a" if g not in ref_exec["applicable"] else "applicable"
        elif g not in ref_exec["applicable"]:
            got = "n/a"
        else:
            got = "pass" if g in ref_exec["passed"] else "fail"
        if exp != "either" and got != exp:
            probs.append(f"{label}: expected {exp}, reference gave {got}")
    return probs
