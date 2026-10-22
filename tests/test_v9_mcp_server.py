"""The ifc MCP server (aec_kg/mcp_server.py) and the Claude runner's stream digest.

Graph calls are faked; one test speaks real MCP over stdio to a server subprocess and only uses
generate_ids, which needs no graph.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

import aec_kg.mcp_server as srv
from eval.generate_claude import digest, build_command, mcp_config, BUILTIN_TOOLS

STATUS = ["NEW", "EXISTING", "DEMOLISH", "TEMPORARY", "OTHER", "NOTKNOWN", "UNSET"]
RAMP_PSET = {"pset_code": "Pset_RampCommon", "pset_name": "Ramp Common", "pset_definition": "x",
             "applies_to": ["IfcRamp"],
             "properties": [{"code": "FireExit", "ifc_type": "IFCBOOLEAN", "allowed_values": []},
                            {"code": "FireRating", "ifc_type": "IFCLABEL", "allowed_values": []},
                            {"code": "Status", "ifc_type": "IFCLABEL", "allowed_values": [{"Code": v} for v in STATUS]}]}


def doc(props):
    return {"info": {"title": "Ramps"},
            "specifications": [{"name": "s", "ifcVersion": "IFC4X3_ADD2",
                                "applicability": {"entity": {"name": {"simpleValue": "IFCRAMP"}}},
                                "requirements": {"properties": props}}]}


def prop(name, value=None, dtype=None, pset="Pset_RampCommon"):
    p = {"propertySet": {"simpleValue": pset}, "baseName": {"simpleValue": name}}
    if value is not None:
        p["value"] = value
    if dtype:
        p["dataType"] = dtype
    return p


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "get_pset_detail", lambda code: RAMP_PSET if code == "Pset_RampCommon"
                        else {"pset_code": code, "properties": []})
    monkeypatch.setattr(srv, "get_class_index", lambda code: {"class_code": code, "property_sets": {"Pset_RampCommon": ["FireExit", "FireRating", "Status"]}})
    monkeypatch.setattr(srv, "list_classes", lambda term: [{"code": "IfcRamp", "name": "Ramp", "definition": "d" * 300}])
    s = srv._State()
    s.ctx.request_text = "Indication whether this object is designed to serve as an exit in the case of fire"
    s.out_dir, s.out_name = tmp_path, "item.ids"
    monkeypatch.setattr(srv, "STATE", s)
    return s


def test_tools_are_registered_with_the_two_step_shape():
    names = {t.name for t in asyncio.run(srv.server.list_tools())}
    assert names == {"search_classes", "query_class", "query_pset", "query_class_structure", "generate_ids"}
    assert "Record vs. require" in srv.INSTRUCTIONS and "query_pset" in srv.INSTRUCTIONS


def test_query_pset_feeds_the_request_checks(state):
    srv.query_pset("Pset_RampCommon")
    assert "FireExit" in state.ctx.known_properties["Pset_RampCommon"]
    out = srv.generate_ids(doc([prop("FireExit", {"simpleValue": "TRUE"})]))
    assert "request_errors" in out and "pinned to 'TRUE'" in out["request_errors"][0]
    assert state.generate_failures == 1 and not (state.out_dir / "item.ids").exists()


def test_generate_ids_writes_the_file_and_summarises(state):
    srv.query_pset("Pset_RampCommon")
    out = srv.generate_ids(doc([prop("FireExit", dtype="IFCBOOLEAN"),
                               prop("Status", {"restriction": {"enumerations": STATUS}}, dtype="IFCLABEL")]))
    assert out["success"] and Path(out["path"]).name == "item.ids"
    xml = Path(out["path"]).read_text(encoding="utf-8")
    assert "IFCRAMP" in xml and "NOTKNOWN" in xml
    assert out["summary"][0]["properties"] == ["Pset_RampCommon.FireExit", "Pset_RampCommon.Status"]
    assert state.generate_success


def test_generate_ids_accepts_a_json_string_and_stops_after_four_failures(state):
    bad = json.dumps({"info": {"title": "t"}, "specifications": []})
    outs = [srv.generate_ids(bad) for _ in range(5)]
    assert all("error" in o for o in outs)
    assert "final_attempt" in outs[3] and outs[4].get("stop") is True


def test_search_classes_trims_definitions(state):
    out = srv.search_classes("ramp")
    assert out[0]["code"] == "IfcRamp" and len(out[0]["definition"]) <= 161


def test_server_speaks_mcp_over_stdio(tmp_path):
    """Real transport: spawn the server, list tools, call generate_ids (no graph needed)."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
           "IDS_OUTPUT_DIR": str(tmp_path), "IDS_OUTPUT_NAME": "stdio.ids",
           "IDS_REQUEST_TEXT": "Walls must have a fire rating.", "NEO4J_URI": "bolt://127.0.0.1:1"}

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "aec_kg.mcp_server"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                tools = await s.list_tools()
                names = {t.name for t in tools.tools}
                d = {"info": {"title": "Walls"},
                     "specifications": [{"name": "w", "ifcVersion": "IFC4X3_ADD2",
                                         "applicability": {"entity": {"name": {"simpleValue": "IFCWALL"}}},
                                         "requirements": {"properties": [prop("FireRating", dtype="IFCLABEL", pset="Pset_WallCommon")]}}]}
                res = await s.call_tool("generate_ids", {"ids": d})
                return init, names, res

    init, names, res = asyncio.run(go())
    assert "generate_ids" in names and "query_pset" in names
    assert "Record vs. require" in (init.instructions or "")
    payload = getattr(res, "structured_content", None) or json.loads(res.content[0].text)
    payload = payload.get("result", payload)
    assert payload["success"] is True and (tmp_path / "stdio.ids").exists()


# ---------------------------------------------------------------- the runner's parsing
def test_digest_reconstructs_calls_tokens_and_result():
    events = [
        {"type": "system", "subtype": "init", "model": "claude-sonnet-5-5", "tools": ["mcp__ifc__query_class", "mcp__ifc__generate_ids"],
         "mcp_servers": [{"name": "ifc", "status": "connected"}], "apiKeySource": "none", "permissionMode": "dontAsk"},
        {"type": "assistant", "message": {"model": "claude-sonnet-5-5", "stop_reason": "tool_use",
                                          "usage": {"input_tokens": 100, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 500, "output_tokens": 40},
                                          "content": [{"type": "tool_use", "id": "t1", "name": "mcp__ifc__query_class", "input": {"class_code": "IfcWall"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": json.dumps({"property_sets": {"Pset_WallCommon": ["FireRating"]}})}]}]}},
        {"type": "assistant", "message": {"model": "claude-sonnet-5-5", "stop_reason": "tool_use",
                                          "usage": {"input_tokens": 50, "cache_read_input_tokens": 2600, "output_tokens": 120},
                                          "content": [{"type": "tool_use", "id": "t2", "name": "mcp__ifc__generate_ids", "input": {"ids": {}}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": json.dumps({"success": True, "path": "x.ids"})}]}},
        {"type": "assistant", "message": {"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 30},
                                          "content": [{"type": "text", "text": "Done: walls need a FireRating."}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Done: walls need a FireRating.",
         "total_cost_usd": 0.0123, "num_turns": 3, "duration_ms": 4000, "session_id": "s"},
    ]
    d = digest(events)
    assert [c["tool"] for c in d["tool_calls"]] == ["query_class", "generate_ids"]
    assert d["tool_calls"][1]["result"] == {"success": True, "path": "x.ids"}
    assert sum(c["prompt_tokens"] for c in d["llm_calls"]) == 100 + 2000 + 500 + 50 + 2600 + 10
    assert sum(c["cached_tokens"] for c in d["llm_calls"]) == 4600
    assert d["result"]["total_cost_usd"] == 0.0123 and d["answer"].startswith("Done")
    assert d["init"]["apiKeySource"] == "none"


def test_command_isolates_the_run_and_config_carries_the_item_env(tmp_path):
    flags = {"--mcp-config", "--strict-mcp-config", "--allowedTools", "--disallowedTools", "--permission-mode",
             "--system-prompt-file", "--output-format", "--verbose", "--model", "--max-turns",
             "--no-session-persistence", "--tools"}
    cmd = build_command("claude", flags, "claude-sonnet-5-5", tmp_path / "m.json", 12)
    assert "--strict-mcp-config" in cmd and "dontAsk" in cmd and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__ifc__*"
    assert all(t in cmd for t in BUILTIN_TOOLS) and cmd[cmd.index("--tools") + 1] == ""
    cfg = mcp_config(tmp_path / "req.txt", tmp_path, "item.ids", {"NEO4J_URI": "bolt://x", "NEO4J_PASSWORD": ""})
    env = cfg["mcpServers"]["ifc"]["env"]
    assert env["IDS_OUTPUT_NAME"] == "item.ids" and env["NEO4J_URI"] == "bolt://x" and "NEO4J_PASSWORD" not in env
    assert cfg["mcpServers"]["ifc"]["args"] == ["-m", "aec_kg.mcp_server"]
