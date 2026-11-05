"""Checks of a generated IDS document against the request it came from.

The Pydantic models (``aec_kg.ids.models``) reject shapes that cannot mean anything. These
checks reject content the request does not support. They run inside ``generate_ids`` so a
rejected document goes back to the model as a tool error, like a validation error, and the
model repairs it in the same turn.

What they catch (every one observed in the v8 evaluation):

* a property name that cannot exist (``"Fire Rating"`` — whitespace) or that the knowledge
  graph does not list for a standard property set (``Pset_ColumnCommon`` has ``FireRating``);
* a Boolean pinned to a value where the request only asks for the property to be recorded
  ("Angabe, ob ...", "indication whether ..."; ``FireExit = TRUE``);
* an enumeration that is a strict subset of the property's IFC enumeration while the request
  names no subset (``Status`` without OTHER/NOTKNOWN/UNSET);
* an exact value, enumeration member or numeric bound that appears neither in the request
  nor in the property's IFC allowed values (``REI 90``; ``RequiredSlope <= 0.06``).

Only requirements are checked: in the IDS model here applicability holds the entity facet
alone, and selecting elements by a value is what applicability is for.

The checks need the request text and, for the graph-backed ones, the property sets the
conversation has looked up. ``main_orchestrator`` supplies both; without them only the
offline checks run. ``set_request_checks(False)`` turns everything off (eval ablation).
"""
from __future__ import annotations

import collections
import difflib
import re
from dataclasses import dataclass, field

GUARDS: collections.Counter = collections.Counter()
ENABLED = True

# How many failed generate_ids calls a turn may make before the tool stops accepting them.
MAX_GENERATE_FAILURES = 4

BOOLEAN_TYPES = {"IFCBOOLEAN", "IFCLOGICAL"}
STANDARD_PSET = re.compile(r"^(Pset_|Qto_)", re.I)

# A request states a Boolean value only when it says so in the imperative. A question
# ("whether ...", "ob ... (JA) oder ... (NEIN)") asks for the property, not for a value, and
# a conditional ("nur das letzte Element ist TRUE") is not a blanket requirement either.
_DIRECTIVE = re.compile(
    r"(\b(must|shall|should|has to|have to|needs? to|is required to|are required to|is to|are to)"
    r"\s+be\s+(set\s+to\s+)?(true|false|wahr|falsch)\b)"
    r"|(\b(muss|müssen|soll|sollen)\b[^.;\n]{0,30}\b(wahr|falsch|true|false)\b)"
    r"|(\b(set|gesetzt)\s+(to|auf)\s+(true|false|wahr|falsch)\b)"
    r"|(=\s*(true|false|wahr|falsch)\b)",
    re.I)


def set_request_checks(enabled: bool) -> None:
    global ENABLED
    ENABLED = enabled


@dataclass
class RequestContext:
    """What the checks may compare a document against."""
    request_text: str | None = None
    # pset code -> prop code -> {"ifc_type": str | None, "allowed_values": set[str]}
    known_properties: dict = field(default_factory=dict)

    def learn(self, class_result: dict) -> None:
        """Remember the property sets a query_class result listed."""
        for pset, body in (class_result.get("property_sets") or {}).items():
            slot = self.known_properties.setdefault(pset, {})
            for p in body.get("properties") or []:
                code = p.get("code")
                if not code:
                    continue
                allowed = set()
                for a in p.get("allowed_values") or []:
                    if isinstance(a, dict):
                        v = a.get("Code") or a.get("code") or a.get("Value") or a.get("value")
                    else:
                        v = a
                    if v:
                        allowed.add(str(v))
                slot[code] = {"ifc_type": p.get("ifc_type"), "allowed_values": allowed}


# --------------------------------------------------------------------------- normalisation
def _norm(s: str) -> str:
    """Lower-case, single spaces, digits without thousands separators, decimal point."""
    s = s.casefold()
    s = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", s)          # 10.000 / 10,000 -> 10000
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)                   # 0,06 -> 0.06
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _number_in_text(v: str, text: str) -> bool:
    """A bound like '0.06' may be written '0,06', '0.060' or '6 %' in the request. Accept the
    first two; a percentage is a different number and must be stated as the bound itself."""
    try:
        x = float(v)
    except ValueError:
        return False
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        try:
            if abs(float(m.group()) - x) <= 1e-9 * max(1.0, abs(x)):
                return True
        except ValueError:
            continue
    return False


def stated(value: str, request_norm: str) -> bool:
    v = _norm(value)
    if not v:
        return True
    if v in request_norm:
        return True
    return _number_in_text(v, request_norm)


def _suggest(name: str, known: list[str], n: int = 3) -> list[str]:
    """Nearest existing names: shared stem first (FireResistance -> FireRating), then fuzzy."""
    stem = name[:4].casefold()
    out = [k for k in known if k[:4].casefold() == stem and k != name]
    for k in difflib.get_close_matches(name, known, n=n, cutoff=0.5):
        if k not in out:
            out.append(k)
    return out[:n]


# --------------------------------------------------------------------------- the checks
def _sv(x) -> str | None:
    return x.simpleValue if x is not None and x.simpleValue is not None else None


def check_document(doc, ctx: RequestContext | None) -> list[str]:
    """Problems in `doc` (an IdsDocument) that the request does not support. Empty = fine."""
    if not ENABLED:
        return []
    ctx = ctx or RequestContext()
    req = _norm(ctx.request_text) if ctx.request_text else None
    directive = bool(ctx.request_text and _DIRECTIVE.search(ctx.request_text))
    problems: list[str] = []

    for si, spec in enumerate(doc.specifications):
        props = (spec.requirements.properties if spec.requirements else None) or []
        for pi, p in enumerate(props):
            where = f"specifications[{si}].requirements.properties[{pi}]"
            pset, name = _sv(p.propertySet), _sv(p.baseName)
            label = f"{pset or '<pattern>'}.{name or '<pattern>'}"

            # 1. the name itself: standard property names are single tokens; a user-defined set
            #    (custom name, or a pattern such as ^(?!(Pset_|Qto_)).+) may use the request's words
            if name is not None and re.search(r"\s", name) and pset and STANDARD_PSET.match(pset):
                GUARDS["property_name_whitespace"] += 1
                problems.append(
                    f"{where}: baseName {name!r} contains whitespace. IFC property names are single "
                    f"tokens (e.g. 'FireRating'); copy the 'code' field from query_class exactly.")
                continue

            # 2. the name must exist in a standard property set the conversation looked up
            known = ctx.known_properties.get(pset) if pset else None
            if name is not None and pset and STANDARD_PSET.match(pset) and known is not None \
                    and name not in known:
                GUARDS["property_not_in_pset"] += 1
                close = _suggest(name, list(known))
                hint = f" Did you mean {', '.join(close)}?" if close else ""
                problems.append(
                    f"{where}: {pset} has no property {name!r} in the knowledge graph.{hint} Use a "
                    f"name query_class listed for {pset}, or a custom property set for a custom property.")
                continue

            if p.value is None:
                continue
            prop_info = (known or {}).get(name) if name else None
            allowed = (prop_info or {}).get("allowed_values") or set()
            allowed_cf = {a.casefold() for a in allowed}
            dtype = (p.dataType or (prop_info or {}).get("ifc_type") or "").upper()

            # 3. a Boolean pinned to a value. An enumeration of both TRUE and FALSE constrains
            #    nothing and is left alone; a one-member enumeration is a pin like a simpleValue.
            r = p.value.restriction
            pinned = p.value.simpleValue
            if dtype in BOOLEAN_TYPES and r is not None and r.enumerations:
                members = {e.strip().upper() for e in r.enumerations}
                if members >= {"TRUE", "FALSE"}:
                    continue
                if len(members) == 1:
                    pinned = next(iter(members))
            if dtype in BOOLEAN_TYPES and pinned is not None and not directive:
                GUARDS["boolean_pinned_without_directive"] += 1
                problems.append(
                    f"{where}: {label} is pinned to {pinned!r}, but the request does not "
                    f"say the value must be that. 'Indication whether ...' / 'Angabe, ob ...' asks for "
                    f"the property to be recorded. Omit 'value' so the property is required to exist "
                    f"with either value; pin it only when the request says it must be TRUE or FALSE.")
                continue

            if req is None or dtype in BOOLEAN_TYPES:
                continue

            if p.value.simpleValue is not None:
                v = p.value.simpleValue
                if dtype not in BOOLEAN_TYPES and v.casefold() not in allowed_cf and not stated(v, req):
                    GUARDS["value_not_in_request"] += 1
                    problems.append(
                        f"{where}: {label} = {v!r}, but the request does not state this value and it "
                        f"is not one of the property's IFC values. Use only values the request gives; "
                        f"if it gives none, omit 'value' and require the property to be present.")
            elif r is not None:
                if r.enumerations:
                    given = list(r.enumerations)
                    untraced = [e for e in given if e.casefold() not in allowed_cf and not stated(e, req)]
                    if untraced:
                        GUARDS["enumeration_member_not_in_request"] += 1
                        problems.append(
                            f"{where}: {label} enumeration contains {untraced!r}, which the request "
                            f"does not state and which are not IFC values of this property. Keep only "
                            f"values from the request or from query_class allowed_values.")
                    elif allowed and set(e.casefold() for e in given) < allowed_cf:
                        named = [e for e in given if stated(e, req)]
                        if len(named) < len(given):
                            GUARDS["enumeration_subset_not_named"] += 1
                            missing = sorted(allowed - {e for e in allowed if e.casefold() in
                                                        {g.casefold() for g in given}})
                            problems.append(
                                f"{where}: {label} lists {len(given)} of the property's {len(allowed)} "
                                f"IFC values and the request does not name that subset. Use the complete "
                                f"allowed_values list (missing: {missing}) unless the request restricts it.")
                for bound in ("minInclusive", "maxInclusive", "minExclusive", "maxExclusive"):
                    b = getattr(r, bound, None)
                    if b is not None and not stated(str(b), req):
                        GUARDS["bound_not_in_request"] += 1
                        problems.append(
                            f"{where}: {label} {bound}={b!r}, but the request states no such number. "
                            f"Omit the bound and require the property to be present, or use the number "
                            f"the request gives.")
    return problems


# --------------------------------------------------------------------------- the reply
_CLAIMS = re.compile(
    r"\b(attached|is attached|has been attached|generated successfully|successfully generated|"
    r"file is ready|download(?:able)? (?:the )?\.?ids|angehängt|erfolgreich (?:generiert|erstellt))\b", re.I)

NO_FILE_NOTE = ("\n\n[No IDS file was produced in this turn: generate_ids did not succeed, so there is "
                "nothing attached.]")


def reconcile_attachment_claim(answer: str, had_success: bool) -> str:
    """The model may describe a file that does not exist. If generate_ids never succeeded in
    this turn and the reply claims otherwise, say so in the reply itself."""
    if had_success or not answer:
        return answer
    if _CLAIMS.search(answer):
        GUARDS["attachment_claim_corrected"] += 1
        return answer.rstrip() + NO_FILE_NOTE
    return answer
