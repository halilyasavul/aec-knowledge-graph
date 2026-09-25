"""Shared paths and helpers for the NL->IDS evaluation loop."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
TESTSET_DIR = EVAL_DIR / "nl_to_ids_testset"
SPEC_TASKS = TESTSET_DIR / "spec_tasks.jsonl"
RUNS_DIR = EVAL_DIR / "runs"

# The only three values the IDS 1.0 XSD accepts in ifcVersion.
XSD_IFC_VERSIONS = {"IFC2X3", "IFC4", "IFC4X3_ADD2"}


def load_tasks(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def safe_name(item_id: str) -> str:
    """Filesystem-safe name for an item id ('#', '/', '\\' and friends)."""
    return re.sub(r"[#/\\:*?\"<>| ]", "_", item_id.replace("#", "__"))


def graph_psets(run_dir: Path) -> dict[str, set] | None:
    """{pset code: {property codes}} from the knowledge graph, cached in the run dir."""
    snap = Path(run_dir) / "graph_psets.json"
    if not snap.exists():
        try:
            from aec_kg.main_orchestrator import _run_cypher_safe
            res = _run_cypher_safe("MATCH (ps:PropertySet) OPTIONAL MATCH (ps)-[:HAS_PROPERTY]->(p:Property) "
                                   "RETURN ps.code AS ps, collect(p.code) AS props")
            if "error" in res:
                raise RuntimeError(res["error"])
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps({r["ps"]: sorted(r["props"]) for r in res["records"]}))
        except Exception as e:
            print(f"  ! graph unavailable ({e}); IFC-only and hallucinated-pset checks disabled", file=sys.stderr)
            return None
    return {k: set(v) for k, v in json.loads(snap.read_text()).items()}


def _names(v: str | None) -> list:
    if v and v.startswith("RESTRICTION("):
        return re.findall(r"enumeration=([^,)]+)", v) or [None]
    return [v]


def ifc_only(item: dict, psets: dict) -> bool:
    """Every required property is a standard IFC property in the graph (pset and name).
    Attribute/entity/material facets are IFC by definition. Project-specific sets such as
    WienBV_* or ePset_OMA_* cannot be found from IFC alone, so those items are excluded."""
    for f in item["target"]:
        if f["facet"] != "property":
            continue
        for ps in _names(f.get("propertySet")):
            if ps not in psets or any(b not in psets[ps] for b in _names(f.get("baseName"))):
                return False
    return True


def graph_property_types(run_dir) -> dict | None:
    """{pset: {property: [ifc_type, source]}} from the graph, cached in the run dir.

    `source` is how ingestion resolved the type: bsdd_text | qto_kind | string_default | omitted.
    """
    snap = Path(run_dir) / "graph_ptypes.json"
    if not snap.exists():
        try:
            from aec_kg.main_orchestrator import _run_cypher_safe
            res = _run_cypher_safe(
                "MATCH (ps:PropertySet)-[:HAS_PROPERTY]->(p:Property) "
                "RETURN ps.code AS ps, p.code AS prop, p.ifc_type AS t, p.ifc_type_source AS src")
            if "error" in res:
                raise RuntimeError(res["error"])
            out: dict = {}
            for r in res["records"]:
                out.setdefault(r["ps"], {})[r["prop"]] = [r["t"], r["src"]]
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps(out))
        except Exception as e:
            print(f"  ! graph unavailable ({e}); dataType provenance disabled", file=sys.stderr)
            return None
    return json.loads(snap.read_text())


def graph_allowed_values(run_dir) -> dict | None:
    """{pset: {property: [allowed value codes]}} from the graph, cached in the run dir."""
    snap = Path(run_dir) / "graph_allowed.json"
    if not snap.exists():
        try:
            from aec_kg.main_orchestrator import _run_cypher_safe
            res = _run_cypher_safe(
                "MATCH (ps:PropertySet)-[:HAS_PROPERTY]->(p:Property) "
                "RETURN ps.code AS ps, p.code AS prop, p.allowed_values AS av")
            if "error" in res:
                raise RuntimeError(res["error"])
            out: dict = {}
            for r in res["records"]:
                vals = json.loads(r["av"]) if r["av"] else []
                out.setdefault(r["ps"], {})[r["prop"]] = [v.get("Code") for v in vals if v.get("Code")]
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps(out))
        except Exception as e:
            print(f"  ! graph unavailable ({e}); value-list determinacy disabled", file=sys.stderr)
            return None
    return json.loads(snap.read_text())
