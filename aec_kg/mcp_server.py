"""The IFC knowledge graph as an MCP server.

    python -m aec_kg.mcp_server            # stdio; add to Claude Code / Claude Desktop / any client

Tools (two-step retrieval, v9):
  search_classes(term)            IFC classes whose code or name contains `term`
  query_class(class_code)         the class's property sets with property codes only (~6k chars)
  query_pset(pset_code)           one property set in full: ifc_type, allowed values, definitions
  query_class_structure(class)    EXPRESS attributes (PredefinedType enum, Name, ...), inheritance
  generate_ids(ids)               validate (Pydantic -> request checks -> XSD), write the .ids file

The authoring rules travel as the server's `instructions`, so every client gets them.
`generate_ids` applies the same request checks as the Gemini app (aec_kg.ids.request_checks):
the request text comes from IDS_REQUEST_TEXT / IDS_REQUEST_FILE (set by the eval runner) or
from the tool's `request_text` argument; the property sets to check against are the ones
`query_pset` returned in this process.

Environment:
  IDS_OUTPUT_DIR     where generated files go (default ./ids_output)
  IDS_OUTPUT_NAME    fixed file name for the next successful generate_ids (the runner sets it)
  IDS_REQUEST_TEXT / IDS_REQUEST_FILE   the request, for the fidelity checks
  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD   as for the rest of aec_kg (.env is read)

Nothing is printed to stdout: stdio is the protocol channel. Logging goes to stderr.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from aec_kg.ids.pipeline import generate_ids_from_json
from aec_kg.ids.request_checks import MAX_GENERATE_FAILURES, RequestContext
from aec_kg.neuro_agent import get_class_index, get_class_structure, get_pset_detail, list_classes

logging.basicConfig(level=os.getenv("IFC_MCP_LOG", "WARNING"), stream=sys.stderr,
                    format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
You are connected to a knowledge graph of the IFC 4.3 schema (bSDD property sets and
properties with their IDS data types and allowed values; EXPRESS attributes, enumerations and
inheritance). Use it to answer IFC questions and to author buildingSMART IDS 1.0 files.

Authoring an IDS from a request:
1. Find the class: query_class(<IfcClass>) gives its property sets and property codes only.
   search_classes if the class name is unsure. query_class_structure for attributes such as
   Name, Description, PredefinedType and their enumerations.
2. Choose the property set(s) the request needs and fetch each ONE with query_pset. Copy
   "code" exactly as baseName and "ifc_type" exactly as dataType (never derive it from the
   coarse data_type; omit dataType if ifc_type is missing). Never invent a name or translate
   one; a property query_pset does not list does not exist in that set. A genuinely custom
   property goes in a custom property set (not Pset_/Qto_).
3. Record vs. require: "indication whether ...", "Angabe, ob ... (JA/NEIN)" ask for the property
   to be RECORDED: require it with NO value. Pin a Boolean only when the request says it must be
   TRUE or FALSE for every element.
4. Values come from the request or from allowed_values, nowhere else: no invented fire-rating
   classes, bounds or example values. When the request names no value, require presence only.
   When it points at a property's standard values ("Standard-Werte", "the IFC values", "as in
   <...>Enum"), use the COMPLETE allowed_values list, plus any further values it names.
5. Coverage: every requirement sentence gets a facet; sentences that only explain what the
   element is get none. Applicability holds the entity (UPPERCASE, e.g. IFCWALL) and, when the
   request restricts it, its predefinedType. When the request selects elements by a value
   (rooms named "Room A", slabs whose slope is under 0.05), that attribute or property goes in
   applicability too, one specification per selection.
6. Call generate_ids with the structured document. It rejects shapes that mean nothing
   (validation_errors), content the request does not support (request_errors) and XSD problems
   (xsd_errors): fix exactly what it names and call again. After its fourth failure it stops;
   then say that no file could be produced and why. A file exists only when generate_ids
   returned success; never describe one otherwise, and never paste IDS XML into the reply.

generate_ids document shape:
  {"info": {"title": str},
   "specifications": [{"name": str, "ifcVersion": "IFC4X3_ADD2",
      "applicability": {"entity": {"name": {"simpleValue": "IFCWALL"},
                                   "predefinedType": {"simpleValue": "SOLIDWALL"}}},
      "requirements": {"properties": [{"propertySet": {"simpleValue": "Pset_WallCommon"},
                                       "baseName": {"simpleValue": "FireRating"},
                                       "dataType": "IFCLABEL",
                                       "value": {"restriction": {"enumerations": ["REI 30", "REI 60"]}}}],
                       "attributes": [{"name": {"simpleValue": "Name"}}]}}]}
  Also in "requirements", only when the request asks for them:
    "partOf": [{"entity": {"name": {"simpleValue": "IFCBUILDINGSTOREY"}},
                "relation": "IFCRELCONTAINEDINSPATIALSTRUCTURE"}]   (relation optional: also
       IFCRELAGGREGATES, IFCRELASSIGNSTOGROUP, IFCRELNESTS; cardinality required|prohibited)
    "classifications": [{"system": {"simpleValue": "..."}, "value": {...}}]   (value optional)
    "materials": [{"value": {...}}]   (value optional: any material)
  "applicability" may also hold "attributes" / "properties" (and partOf, classifications,
  materials) in the same shapes, without cardinality, to select the elements, e.g.
    "applicability": {"entity": {"name": {"simpleValue": "IFCSPACE"}},
                      "attributes": [{"name": {"simpleValue": "Name"}, "value": {"simpleValue": "Room A"}}]}
  A value is {"simpleValue": "EXACT"} or {"restriction": {"enumerations": [...]}} or
  {"restriction": {"pattern": "regex"}} or {"restriction": {"minInclusive": "0.45"}} (also
  maxInclusive / minExclusive / maxExclusive). Omit "value" to require presence only.
"""

server = MCPServer("ifc", instructions=INSTRUCTIONS,
                   description="IFC 4.3 knowledge graph: classes, property sets, attributes; IDS generation")


# --------------------------------------------------------------------------- per-process state
class _State:
    def __init__(self):
        text = os.getenv("IDS_REQUEST_TEXT")
        f = os.getenv("IDS_REQUEST_FILE")
        if not text and f and Path(f).exists():
            text = Path(f).read_text(encoding="utf-8")
        self.ctx = RequestContext(request_text=text or None)
        self.generate_failures = 0
        self.generate_success = False
        self.out_dir = Path(os.getenv("IDS_OUTPUT_DIR", "ids_output"))
        self.out_name = os.getenv("IDS_OUTPUT_NAME")
        self.last_path: Path | None = None


STATE = _State()


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s[:60] or "ids"


# --------------------------------------------------------------------------- tools
@server.tool()
def search_classes(term: str) -> list[dict]:
    """IFC classes whose code or name contains `term` (case-insensitive). Returns code, name
    and a one-line definition for each; at most 40 matches."""
    out = []
    for c in list_classes(term)[:40]:
        d = (c.get("definition") or "").strip().replace("\n", " ")
        out.append({"code": c["code"], "name": c["name"], "definition": d[:160] + ("…" if len(d) > 160 else "")})
    return out


@server.tool()
def query_class(class_code: str) -> dict:
    """A class's property sets with their property codes only (no definitions, no values):
    the index to choose from. Then fetch the set you need with query_pset. Example:
    query_class("IfcWall") -> {"property_sets": {"Pset_WallCommon": ["FireRating", ...], ...}}."""
    return get_class_index(class_code)


@server.tool()
def query_pset(pset_code: str) -> dict:
    """One property set in full. Each property has "code" (use as baseName), "ifc_type" (use
    as dataType), "data_type", "definition" and "allowed_values" (the IFC enumeration, if any).
    Example: query_pset("Pset_WallCommon")."""
    detail = get_pset_detail(pset_code)
    if detail.get("properties"):
        STATE.ctx.learn({"property_sets": {detail["pset_code"]: {"properties": detail["properties"]}}})
    return detail


@server.tool()
def query_class_structure(class_code: str) -> dict:
    """EXPRESS structure of a class: attributes (Name, Description, PredefinedType, ...) with
    types and enumerations, the inheritance chain and WHERE rules. Use for attribute facets and
    for the PredefinedType values of a class."""
    return get_class_structure(class_code)


@server.tool()
def generate_ids(ids: dict | str, request_text: str | None = None) -> dict:
    """Validate an IDS document and write the .ids file. `ids` is the document (object, or a
    JSON string) in the shape given in the server instructions. `request_text`: the user's
    request verbatim, if the server was not started with it; it lets the checks compare values
    against what was asked. Returns {"success": true, "path": ..., "summary": ...} or an error
    with validation_errors / request_errors / xsd_errors to fix. Stops after four failures."""
    if STATE.generate_failures >= MAX_GENERATE_FAILURES:
        return {"error": f"generate_ids has failed {STATE.generate_failures} times and will not be "
                         "retried. Tell the user that no IDS file could be produced and quote the "
                         "last error.", "stop": True}
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except json.JSONDecodeError as e:
            STATE.generate_failures += 1
            return {"error": f"ids is not valid JSON: {e}"}
    if request_text and not STATE.ctx.request_text:
        STATE.ctx.request_text = request_text
    result = generate_ids_from_json(ids, STATE.ctx)
    if not result.get("success"):
        STATE.generate_failures += 1
        if STATE.generate_failures >= MAX_GENERATE_FAILURES:
            result["final_attempt"] = ("This was the last permitted attempt. Do not call generate_ids "
                                       "again; report the failure.")
        return result
    STATE.generate_success = True
    STATE.out_dir.mkdir(parents=True, exist_ok=True)
    name = STATE.out_name or f"{_slug(ids.get('info', {}).get('title', 'ids'))}_{int(time.time())}.ids"
    path = STATE.out_dir / name
    path.write_text(result["ids_xml"], encoding="utf-8")
    STATE.last_path = path
    specs = ids.get("specifications") or []
    summary = []
    for sp in specs:
        ent = ((sp.get("applicability") or {}).get("entity") or {}).get("name", {})
        ent = ent.get("simpleValue") if isinstance(ent, dict) else ent
        req = sp.get("requirements") or {}
        props = [f"{(p.get('propertySet') or {}).get('simpleValue', '?')}.{(p.get('baseName') or {}).get('simpleValue', '?')}"
                 for p in req.get("properties") or []]
        attrs = [(a.get("name") or {}).get("simpleValue", "?") for a in req.get("attributes") or []]
        item = {"applies_to": ent, "properties": props, "attributes": attrs}
        part_of = [((p.get("entity") or {}).get("name") or {}).get("simpleValue", "?")
                   for p in req.get("partOf") or req.get("partOfs") or []]
        n_cls = len(req.get("classifications") or req.get("classification") or [])
        n_mat = len(req.get("materials") or req.get("material") or [])
        if part_of:
            item["part_of"] = part_of
        if n_cls:
            item["classifications"] = n_cls
        if n_mat:
            item["materials"] = n_mat
        summary.append(item)
    return {"success": True, "path": str(path), "spec_count": result["spec_count"], "summary": summary}


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
