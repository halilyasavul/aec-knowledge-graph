"""v10b: the --dictionaries flag of the ifc MCP server and the runner's request_text items.

Graph calls are faked. With the default ('ifc') every tool must return exactly what it returned
before the flag existed; with 'ifc,usbridge' usBridge records are added, tagged by dictionary.
"""
import pytest

import aec_kg.mcp_server as srv
import aec_kg.usbridge as ub
from eval.generate_claude import (REQUEST_HEADER, assert_no_leak_text, mcp_config, request_message)

IFC_CLASSES = [{"code": "IfcBeam", "name": "Beam", "definition": "d"}]
UB_SEARCH = [{"code": "usBridge_PierCap", "name": "Pier Cap", "definition": "top of a pier",
              "dictionary": "usBridge", "ifc_entity": "IFCBEAM", "predefinedType": "PIERCAP"}]
UB_PSET = {"pset_code": "usBrPset_PierCap", "dictionary": "usBridge", "applies_to": ["usBridge_PierCap"],
           "properties": [{"code": "Radius", "ifc_type": "IFCPOSITIVELENGTHMEASURE", "allowed_values": []}]}


@pytest.fixture
def fake_graph(monkeypatch):
    monkeypatch.setattr(srv, "list_classes", lambda term: IFC_CLASSES)
    monkeypatch.setattr(srv, "get_class_index", lambda code: {"class_code": code, "property_sets": {"Pset_BeamCommon": ["Span"]}})
    monkeypatch.setattr(srv, "get_pset_detail", lambda code: {"pset_code": code, "properties": []})
    monkeypatch.setattr(srv, "get_class_structure", lambda code: {"class_code": code, "attributes": []})
    monkeypatch.setattr(ub, "search", lambda term, limit=40: UB_SEARCH)
    monkeypatch.setattr(ub, "class_index", lambda code: ({"class_code": code, "dictionary": "usBridge",
                                                          "ifc_entity": "IFCBEAM", "predefinedType": "PIERCAP",
                                                          "objectType": None, "property_sets": {"usBrPset_PierCap": ["Radius"]}}
                                                         if code.startswith("usBridge_") else None))
    monkeypatch.setattr(ub, "classes_for_ifc", lambda code: [{"code": "usBridge_PierCap", "dictionary": "usBridge"}])
    monkeypatch.setattr(ub, "pset_detail", lambda code: UB_PSET if code == "usBrPset_PierCap" else None)
    s = srv._State()
    monkeypatch.setattr(srv, "STATE", s)
    return s


def test_parse_dictionaries():
    assert srv.parse_dictionaries([], {}) == {"ifc"}
    assert srv.parse_dictionaries(["--dictionaries", "ifc,usbridge"], {}) == {"ifc", "usbridge"}
    assert srv.parse_dictionaries(["--dictionaries=usbridge"], {}) == {"ifc", "usbridge"}
    assert srv.parse_dictionaries([], {"IFC_DICTIONARIES": "ifc,usBridge"}) == {"ifc", "usbridge"}
    with pytest.raises(SystemExit):
        srv.parse_dictionaries(["--dictionaries", "ifc,nope"], {})


def test_default_is_unchanged_and_never_reads_usbridge(fake_graph, monkeypatch):
    monkeypatch.setattr(srv, "DICTIONARIES", frozenset({"ifc"}))
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("usBridge read in ifc mode"))
    for name in ("search", "class_index", "classes_for_ifc", "pset_detail"):
        monkeypatch.setattr(ub, name, boom)
    assert srv.search_classes("beam") == [{"code": "IfcBeam", "name": "Beam", "definition": "d"}]
    assert srv.query_class("IfcBeam") == {"class_code": "IfcBeam", "property_sets": {"Pset_BeamCommon": ["Span"]}}
    assert srv.query_pset("usBrPset_PierCap") == {"pset_code": "usBrPset_PierCap", "properties": []}
    assert srv.query_class_structure("IfcBeam") == {"class_code": "IfcBeam", "attributes": []}


def test_usbridge_mode_adds_tagged_records(fake_graph, monkeypatch):
    monkeypatch.setattr(srv, "DICTIONARIES", frozenset({"ifc", "usbridge"}))
    out = srv.search_classes("pier")
    assert out[0] == {"code": "IfcBeam", "name": "Beam", "definition": "d", "dictionary": "ifc"}
    assert out[1]["dictionary"] == "usBridge" and out[1]["code"] == "usBridge_PierCap"
    qc = srv.query_class("IfcBeam")
    assert qc["dictionary"] == "ifc" and qc["usbridge_classes"][0]["code"] == "usBridge_PierCap"
    assert srv.query_class("usBridge_PierCap")["property_sets"] == {"usBrPset_PierCap": ["Radius"]}
    p = srv.query_pset("usBrPset_PierCap")
    assert p["dictionary"] == "usBridge" and "Radius" in fake_graph.ctx.known_properties["usBrPset_PierCap"]
    st = srv.query_class_structure("usBridge_PierCap")
    assert st["dictionary"] == "usBridge" and st["ifc_entity"] == "IFCBEAM" and st["predefinedType"] == "PIERCAP"


def test_runner_passes_the_flag_only_when_not_default(tmp_path):
    a = mcp_config(tmp_path / "r.txt", tmp_path, "x.ids", {})
    b = mcp_config(tmp_path / "r.txt", tmp_path, "x.ids", {}, "ifc,usbridge")
    assert a["mcpServers"]["ifc"]["args"] == ["-m", "aec_kg.mcp_server"]
    assert b["mcpServers"]["ifc"]["args"] == ["-m", "aec_kg.mcp_server", "--dictionaries", "ifc,usbridge"]


def test_long_messages_go_through_stdin(monkeypatch, tmp_path):
    import eval.generate_claude as gc
    seen = []

    class P:
        stdout, stderr, returncode = '{"type": "result"}\n', "", 0

    monkeypatch.setattr(gc.subprocess, "run", lambda args, **kw: seen.append((args, kw.get("input"))) or P())
    gc.run_claude(["claude", "-p"], "short", tmp_path, 10)
    gc.run_claude(["claude", "-p"], "x" * (gc.STDIN_ABOVE + 1), tmp_path, 10)
    assert seen[0] == (["claude", "-p", "short"], None)
    assert seen[1][0] == ["claude", "-p"] and len(seen[1][1]) == gc.STDIN_ABOVE + 1


def test_request_text_items_are_sent_verbatim_and_checked():
    item = {"id": "usb-idm1-033", "request_text": "Entity: Pier Cap\n  Property Set: Dimensions\n    - Cap Beam Depth",
            "reference_spec_ids": ["usBrSpec_Classes#35"]}
    m = request_message(item)
    assert m == REQUEST_HEADER + item["request_text"]
    assert_no_leak_text(item, m)
    with pytest.raises(AssertionError):
        assert_no_leak_text({**item, "request_text": "Entity: Pier Cap (IFCBEAM PIERCAP)"},
                            request_message({**item, "request_text": "Entity: Pier Cap (IFCBEAM PIERCAP)"}))
    with pytest.raises(AssertionError):
        assert_no_leak_text(item, m + "usBrSpec_Classes#35")
