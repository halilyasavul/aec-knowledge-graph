"""A stand-in for `claude -p` for the v10b dry run: no model, a recorded answer.

Invoked by eval.generate_claude exactly as Claude Code would be (the dry run puts a `claude`
wrapper for this script first on PATH). It reads the runner's --mcp-config, starts that MCP server
with its command, args (incl. --dictionaries) and env, makes the tool calls a model would make —
search_classes, query_class, query_pset, then generate_ids with the recorded document — and prints
Claude Code's stream-json events, so the runner, the server flag, the file paths and the scorer all
run end to end. `--help` prints the flags the runner checks for.

The recorded answer: eval/usbridge/dry_run_answer.json ({"search": term, "class": code,
"psets": [...], "ids": <generate_ids document>}).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLAGS = ["--mcp-config", "--strict-mcp-config", "--allowedTools", "--disallowedTools", "--permission-mode",
         "--system-prompt-file", "--output-format", "--verbose", "--model", "--max-turns", "--no-session-persistence"]


def emit(e: dict):
    print(json.dumps(e), flush=True)


async def run(cfg: dict, answer: dict) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    srv = cfg["mcpServers"]["ifc"]
    params = StdioServerParameters(command=srv["command"], args=srv["args"], env=srv.get("env"))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [f"mcp__ifc__{t.name}" for t in (await s.list_tools()).tools]
            emit({"type": "system", "subtype": "init", "model": "stub-recorded-answer", "tools": tools,
                  "mcp_servers": [{"name": "ifc", "status": "connected"}], "apiKeySource": "none",
                  "permissionMode": "dontAsk", "claude_code_version": "stub", "server_args": srv["args"]})
            calls = [("search_classes", {"term": answer["search"]}), ("query_class", {"class_code": answer["class"]})]
            calls += [("query_pset", {"pset_code": p}) for p in answer["psets"]]
            calls.append(("generate_ids", {"ids": answer["ids"]}))
            for n, (tool, args) in enumerate(calls, 1):
                emit({"type": "assistant", "message": {"id": f"m{n}", "model": "stub-recorded-answer", "stop_reason": "tool_use",
                                                       "usage": {"input_tokens": 0, "output_tokens": 0},
                                                       "content": [{"type": "tool_use", "id": f"t{n}", "name": f"mcp__ifc__{tool}",
                                                                    "input": args}]}})
                res = await s.call_tool(tool, args)
                blocks = [{"type": "text", "text": c.text} for c in res.content or [] if getattr(c, "text", None)]
                emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}",
                                                               "content": blocks,
                                                               "is_error": bool(getattr(res, "isError", None)
                                                                                or getattr(res, "is_error", False))}]}})
            emit({"type": "assistant", "message": {"id": "end", "model": "stub-recorded-answer", "stop_reason": "end_turn",
                                                   "usage": {"input_tokens": 0, "output_tokens": 0},
                                                   "content": [{"type": "text", "text": "stub: recorded answer submitted"}]}})
            emit({"type": "result", "subtype": "success", "is_error": False, "result": "stub: recorded answer submitted",
                  "total_cost_usd": 0.0, "num_turns": len(calls) + 1, "usage": {"output_tokens": 0}})


def main():
    argv = sys.argv[1:]
    if "--help" in argv:
        print("stub claude\n" + "\n".join(FLAGS))
        return
    if "--mcp-config" not in argv:
        print("stub: no --mcp-config", file=sys.stderr)
        sys.exit(2)
    cfg = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
    answer = json.loads((HERE / "dry_run_answer.json").read_text(encoding="utf-8"))
    asyncio.run(run(cfg, answer))


if __name__ == "__main__":
    main()
