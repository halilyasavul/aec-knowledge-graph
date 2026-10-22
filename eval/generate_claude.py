"""Step 2, Claude edition — generate candidate IDS with Claude Code and the ifc MCP server.

    python -m eval.generate_claude --run-id run7-claude-rep1 --ids-file eval/item_lists/probe.json \
        --model claude-sonnet-5-5

One `claude -p` process per item, on the subscription login (no API key), with ONLY the tools
of `aec_kg.mcp_server` (``--strict-mcp-config``, built-ins disallowed, cwd = an empty scratch
directory), the system prompt replaced by eval/claude_system_prompt.md, and
``--output-format stream-json`` parsed into the same ``log.jsonl`` / ``generated/`` layout that
eval/generate.py writes, so eval.score and every analysis run unchanged.

The server writes the .ids file itself (IDS_OUTPUT_DIR / IDS_OUTPUT_NAME) and gets the request
text through IDS_REQUEST_FILE, so the request checks see exactly what the model saw.

    --probe        run one trivial prompt first and print the tools, MCP servers and auth source
                   the run actually had; refuse to continue if a built-in tool is present.

Needs: Claude Code on PATH and logged in, Neo4j reachable with the .env credentials, and the
repository importable by the Python that runs this script (that Python starts the server).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import dotenv_values

from eval.common import RUNS_DIR, SPEC_TASKS, graph_psets, ifc_only, load_tasks, safe_name
from eval.generate import assert_no_leak, build_message, ordered

REPO = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_FILE = REPO / "eval" / "claude_system_prompt.md"
SERVER_NAME = "ifc"
BUILTIN_TOOLS = ["Bash", "Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Glob", "Grep", "LS",
                 "WebFetch", "WebSearch", "Agent", "Task", "TaskStop", "TodoWrite", "Skill",
                 "AskUserQuestion", "EnterPlanMode", "ExitPlanMode", "KillShell", "BashOutput",
                 "SendMessage", "ListAgents", "Monitor", "PowerShell"]
WANTED_FLAGS = ["--mcp-config", "--strict-mcp-config", "--allowedTools", "--disallowedTools",
                "--permission-mode", "--system-prompt-file", "--output-format", "--verbose", "--model",
                "--max-turns", "--no-session-persistence"]
OPTIONAL_FLAGS = ["--tools", "--permission-prompts", "--setting-sources", "--disable-slash-commands"]


# --------------------------------------------------------------------------- claude cli
def find_claude() -> str:
    for name in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(name)
        if p:
            return p
    sys.exit("Claude Code not found on PATH (tried claude, claude.cmd, claude.exe)")


def child_env() -> dict:
    """Our environment minus what a parent Claude Code session (CLI, desktop app, SDK) exports:
    CLAUDECODE, CLAUDE_CODE_* (entrypoint, session id, messaging socket, extra tools),
    CLAUDE_EFFORT, and ANTHROPIC_* (an API key would bill the run to it, not the subscription).
    CLAUDE_CONFIG_DIR stays: it says where the login lives."""
    return {k: v for k, v in os.environ.items()
            if k == "CLAUDE_CONFIG_DIR" or not (k.upper().startswith(("CLAUDE", "ANTHROPIC_")))}


def cli_flags(claude: str) -> set[str]:
    out = subprocess.run([claude, "--help"], capture_output=True, text=True, timeout=60, env=child_env())
    text = out.stdout + out.stderr
    found = {f for f in WANTED_FLAGS + OPTIONAL_FLAGS if f in text}
    # Some builds accept --max-turns and --system-prompt-file without listing them in --help
    # (2.1.296 does). Options are parsed before the action runs, so a missing prompt file fails
    # fast and with no model call when both flags are known, and says "unknown option" if not.
    hidden = [f for f in ("--max-turns", "--system-prompt-file") if f not in found]
    if hidden:
        missing_file = Path(tempfile.gettempdir()) / "ids-eval-no-such-prompt.md"
        out = subprocess.run([claude, "-p", "--max-turns", "1", "--system-prompt-file", str(missing_file), "x"],
                             capture_output=True, text=True, timeout=60, env=child_env())
        if "unknown option" not in (out.stdout + out.stderr):
            found.update(hidden)
    return found


def build_command(claude: str, flags: set[str], model: str, mcp_cfg: Path, max_turns: int,
                  extra_disallowed: list[str] | None = None) -> list[str]:
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(mcp_cfg), "--strict-mcp-config",
           "--allowedTools", f"mcp__{SERVER_NAME}__*",
           "--disallowedTools", *BUILTIN_TOOLS, *(extra_disallowed or []),
           "--permission-mode", "dontAsk",
           "--system-prompt-file", str(SYSTEM_PROMPT_FILE),
           "--model", model, "--max-turns", str(max_turns), "--no-session-persistence"]
    if "--tools" in flags:
        cmd += ["--tools", ""]
    if "--permission-prompts" in flags:
        cmd += ["--permission-prompts", "none"]
    if "--disable-slash-commands" in flags:
        cmd += ["--disable-slash-commands"]
    return cmd


def mcp_config(request_file: Path, out_dir: Path, out_name: str, env_extra: dict) -> dict:
    # Pass the process environment the server needs even if the client does not inherit ours:
    # user site-packages (APPDATA), temp dirs, PATH and the Windows system root.
    env = {k: os.environ[k] for k in ("PATH", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
                                      "HOME", "SYSTEMROOT", "TEMP", "TMP", "PYTHONUSERBASE") if os.environ.get(k)}
    env.update({"PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8",
                "IDS_REQUEST_FILE": str(request_file), "IDS_OUTPUT_DIR": str(out_dir), "IDS_OUTPUT_NAME": out_name})
    env.update({k: v for k, v in env_extra.items() if v})
    return {"mcpServers": {SERVER_NAME: {"type": "stdio", "command": sys.executable,
                                         "args": ["-m", "aec_kg.mcp_server"], "env": env}}}


def neo4j_env() -> dict:
    vals = dotenv_values(REPO / ".env")
    out = {}
    for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        out[k] = os.environ.get(k) or vals.get(k) or ""
    return out


# --------------------------------------------------------------------------- stream parsing
def run_claude(cmd: list[str], message: str, cwd: Path, timeout_s: int) -> tuple[list[dict], str, int]:
    """Run one item; return (events, stderr, returncode). Events are the parsed stream-json lines."""
    proc = subprocess.run(cmd + [message], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout_s, env=child_env())
    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events, proc.stderr, proc.returncode


def _parse_result_content(content):
    """tool_result content is text (or a list of text blocks); the server returns JSON text."""
    if isinstance(content, list):
        content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content
    return content


def digest(events: list[dict]) -> dict:
    """llm_calls, tool_calls, usage and the final result, in eval/generate.py's shapes."""
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    llm_calls, tool_calls, pending = [], [], {}
    call_index = {}                     # message id -> position in llm_calls
    answer_parts = []
    for e in events:
        if e.get("type") == "assistant":
            msg = e.get("message", {})
            u = msg.get("usage") or {}
            call = {"prompt_tokens": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                    + (u.get("cache_creation_input_tokens") or 0),
                    "uncached_prompt_tokens": u.get("input_tokens") or 0,
                    "cached_tokens": u.get("cache_read_input_tokens") or 0,
                    "cache_creation_tokens": u.get("cache_creation_input_tokens") or 0,
                    "output_tokens": u.get("output_tokens") or 0, "thinking_tokens": 0,
                    "model_version": msg.get("model"), "finish_reason": msg.get("stop_reason")}
            # Claude Code emits one assistant event per content block, each carrying the whole
            # message's usage: count a message once (Run 7 was logged before this, 2-3x over).
            mid = msg.get("id")
            if mid is not None and mid in call_index:
                llm_calls[call_index[mid]] = call
            else:
                call_index[mid] = len(llm_calls)
                llm_calls.append(call)
            for block in msg.get("content") or []:
                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    short = name.split("__", 2)[-1] if name.startswith("mcp__") else name
                    pending[block.get("id")] = {"tool": short, "tool_full": name, "args": block.get("input"),
                                                "t": time.time()}
                elif block.get("type") == "text":
                    answer_parts.append(block.get("text", ""))
        elif e.get("type") == "user":
            for block in (e.get("message", {}).get("content") or []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    call = pending.pop(block.get("tool_use_id"), None)
                    if call is None:
                        continue
                    res = _parse_result_content(block.get("content"))
                    s = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
                    tool_calls.append({"tool": call["tool"], "tool_full": call["tool_full"], "args": call["args"], "result": res,
                                       "result_chars": len(s), "delivered_chars": len(s),
                                       "is_error": bool(block.get("is_error"))})
    result = next((e for e in events if e.get("type") == "result"), {})
    return {"init": {"model": init.get("model"), "tools": init.get("tools"), "mcp_servers": init.get("mcp_servers"),
                     "apiKeySource": init.get("apiKeySource"), "permissionMode": init.get("permissionMode"),
                     "claude_code_version": init.get("claude_code_version")},
            "llm_calls": llm_calls, "tool_calls": tool_calls, "result": result,
            "answer": result.get("result") if isinstance(result.get("result"), str) else "\n".join(answer_parts)}


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tasks", default=str(SPEC_TASKS))
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5", help="model id or alias Claude Code accepts")
    ap.add_argument("--all", action="store_true", help="include items needing project-specific property sets")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids-file", help="JSON list of item ids to run (exactly those, in that order)")
    ap.add_argument("--max-turns", type=int, default=14)
    ap.add_argument("--timeout", type=int, default=600, help="seconds per item")
    ap.add_argument("--probe", action="store_true", help="one trivial prompt; print tools/servers/auth and stop")
    args = ap.parse_args(argv)

    claude = find_claude()
    flags = cli_flags(claude)
    missing = [f for f in WANTED_FLAGS if f not in flags]
    if missing:
        sys.exit(f"this Claude Code build lacks flags the runner relies on: {missing}; run `claude --help` and "
                 f"adjust eval/generate_claude.py")
    env_extra = neo4j_env()
    run_dir = RUNS_DIR / args.run_id
    gen_dir = run_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="ids-eval-"))        # empty cwd: nothing to read even if a tool leaked
    req_dir = run_dir / "requests"
    req_dir.mkdir(exist_ok=True)

    if args.probe:
        req = req_dir / "_probe.txt"
        req.write_text("probe", encoding="utf-8")
        cfg = run_dir / "_probe.mcp.json"
        cfg.write_text(json.dumps(mcp_config(req, gen_dir, "_probe.ids", env_extra), indent=1))
        cmd = build_command(claude, flags, args.model, cfg, 4)
        probe_prompt = ("Do three things and report each in one line. 1) Call query_class for IfcWall and give the "
                        "number of property sets. 2) Try to read the file C:\\Windows\\win.ini (or /etc/hosts) with "
                        "any file-reading tool you have and say whether that was possible. 3) Try to run the shell "
                        "command `echo leak` with any shell tool you have and say whether that was possible.")
        events, err, rc = run_claude(cmd, probe_prompt, scratch, 240)
        d = digest(events)
        print(json.dumps(d["init"], indent=1))
        listed = [t for t in (d["init"]["tools"] or []) if not t.startswith(f"mcp__{SERVER_NAME}__")]
        leaked = [c for c in d["tool_calls"] if not c["tool_full"].startswith(f"mcp__{SERVER_NAME}__") and not c["is_error"]]
        print(f"tool calls: {[(c['tool_full'], 'error' if c['is_error'] else 'ok') for c in d['tool_calls']]}")
        print(f"result: {str(d['answer'])[:400]!r}")
        print(f"cost: {d['result'].get('total_cost_usd')}  turns: {d['result'].get('num_turns')}  rc={rc}  "
              f"denials: {d['result'].get('permission_denials')}")
        print(f"llm calls: {len(d['llm_calls'])}  usage: {d['result'].get('usage')}")
        if err.strip():
            print("stderr:", err[-800:])
        if listed:
            print(f"note: built-in tools still listed (should be blocked by permissions): {listed}")
        if leaked:
            sys.exit(f"REFUSING: a built-in tool call succeeded: {[c['tool_full'] for c in leaked]}. "
                     f"Fix the flags before an eval run.")
        if not any(c["tool"] == "query_class" for c in d["tool_calls"]):
            sys.exit("REFUSING: the ifc server's query_class was never called; check the MCP server started "
                     "(stderr above) and that Neo4j is reachable.")
        if d["init"].get("apiKeySource") not in (None, "none", "oauth", "claude.ai"):
            print(f"NOTE: apiKeySource={d['init'].get('apiKeySource')!r} — check this is the subscription, not an API key")
        print("probe ok")
        return

    sys_sha = hashlib.sha256(SYSTEM_PROMPT_FILE.read_bytes()).hexdigest()
    import aec_kg.mcp_server as srv
    instr_sha = hashlib.sha256(srv.INSTRUCTIONS.encode()).hexdigest()
    meta = {"generator": "claude-code", "model": args.model, "system_prompt_sha256": sys_sha,
            "server_instructions_sha256": instr_sha, "max_turns": args.max_turns,
            "builtin_tools_disallowed": BUILTIN_TOOLS, "cli_flags_present": sorted(flags),
            "message_template": build_message({"applies_to": {"entity": "X"}, "requirements": ["R"]}),
            "tasks": str(Path(args.tasks).resolve())}
    meta_path = run_dir / "run.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text())
        for k in ("model", "system_prompt_sha256", "server_instructions_sha256", "message_template"):
            if prev.get(k) != meta.get(k):
                sys.exit(f"refusing to resume {args.run_id}: {k} changed")
    else:
        meta["created"] = dt.datetime.now().isoformat(timespec="seconds")
        meta_path.write_text(json.dumps(meta, indent=2))

    tasks = ordered(load_tasks(args.tasks))
    if args.ids_file:
        wanted = json.loads(Path(args.ids_file).read_text())
        by_id = {t["id"]: t for t in tasks}
        missing_ids = [i for i in wanted if i not in by_id]
        if missing_ids:
            sys.exit(f"ids not found in tasks: {missing_ids}")
        tasks = [by_id[i] for i in wanted]
    elif not args.all:
        psets = graph_psets(run_dir)
        if psets is None:
            sys.exit("graph needed to select IFC-only items (or pass --all / --ids-file)")
        tasks = [t for t in tasks if ifc_only(t, psets)]
    id_map_path = run_dir / "id_map.json"
    id_map = json.loads(id_map_path.read_text()) if id_map_path.exists() else {}
    (run_dir / "order.json").write_text(json.dumps([t["id"] for t in tasks], indent=0))
    log_path = run_dir / "log.jsonl"
    todo = tasks[: args.limit] if args.limit else tasks
    done = ok = 0
    total_cost = 0.0
    for item in todo:
        name = safe_name(item["id"])
        id_map[name] = item["id"]
        out_ids, out_fail = gen_dir / f"{name}.ids", gen_dir / f"{name}.fail.json"
        if out_ids.exists() or out_fail.exists():
            continue
        message = build_message(item["prompt"])
        assert_no_leak(item, message)
        req = req_dir / f"{name}.txt"
        req.write_text(message, encoding="utf-8")
        cfg = run_dir / "requests" / f"{name}.mcp.json"
        cfg.write_text(json.dumps(mcp_config(req, gen_dir, f"{name}.ids", env_extra), indent=1))
        cmd = build_command(claude, flags, args.model, cfg, args.max_turns)
        entry = {"id": item["id"], "file": name, "model": args.model, "model_api_version": None,
                 "temperature": None, "prompt_sent": message, "prompt_chars": len(message),
                 "started": dt.datetime.now().isoformat(timespec="seconds")}
        t0 = time.perf_counter()
        error = None
        try:
            events, err, rc = run_claude(cmd, message, scratch, args.timeout)
        except subprocess.TimeoutExpired:
            events, err, rc, error = [], "", -1, f"timeout after {args.timeout}s"
        entry["wall_ms"] = round((time.perf_counter() - t0) * 1000)
        d = digest(events)
        gen_calls = [c for c in d["tool_calls"] if c["tool"] == "generate_ids"]
        success = [c for c in gen_calls if isinstance(c["result"], dict) and c["result"].get("success")]
        res = d["result"]
        tin = sum(c["prompt_tokens"] for c in d["llm_calls"])
        # the per-event usage holds the output count at stream start; the result event has the total
        tout = (res.get("usage") or {}).get("output_tokens") or sum(c["output_tokens"] for c in d["llm_calls"])
        entry.update({"model_api_version": d["init"].get("model"), "init": d["init"],
                      "llm_calls": d["llm_calls"], "tool_calls": d["tool_calls"],
                      "retries": {"generate_ids_attempts": len(gen_calls),
                                  "generate_ids_failures": len(gen_calls) - len(success)},
                      "input_tokens": tin, "output_tokens": tout,
                      "thinking_tokens": ((res.get("usage") or {}).get("output_tokens_details") or {}).get("thinking_tokens") or 0,
                      "cached_tokens": sum(c["cached_tokens"] for c in d["llm_calls"]),
                      "cost_usd": res.get("total_cost_usd"), "num_turns": res.get("num_turns"),
                      "result_usage": res.get("usage"), "model_usage": res.get("modelUsage"),
                      "result_subtype": res.get("subtype"), "is_error": res.get("is_error"),
                      "permission_denials": res.get("permission_denials"),
                      "answer": d["answer"], "returncode": rc,
                      "stderr_tail": err[-1500:] if err else "",
                      "tool_result_chars_max": max((c["result_chars"] for c in d["tool_calls"]), default=0)})
        total_cost += float(res.get("total_cost_usd") or 0)
        if error:
            entry.update(status="error", error=error)
        elif out_ids.exists() and success:
            entry.update(status="ok", output=str(out_ids.relative_to(run_dir)))
            ok += 1
        else:
            reason = error or (gen_calls[-1]["result"].get("error") if gen_calls and isinstance(gen_calls[-1]["result"], dict)
                               else (f"claude exited {rc}: {err[-300:]}" if rc else "generate_ids never called"))
            out_fail.write_text(json.dumps({"id": item["id"], "reason": reason, "answer": d["answer"]}, indent=1))
            entry.update(status="no_file", error=reason, output=str(out_fail.relative_to(run_dir)))
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        id_map_path.write_text(json.dumps(id_map, indent=1))
        done += 1
        print(f"[{done}] {item['id'][:55]:<55} {entry['status']:<8} {entry['wall_ms']/1000:6.1f}s "
              f"tools={len(d['tool_calls'])} gen={len(gen_calls)} in={tin:,} ${res.get('total_cost_usd') or 0:.3f} "
              f"run=${total_cost:.2f}", flush=True)
    id_map_path.write_text(json.dumps(id_map, indent=1))
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"\n{done} generated this session ({ok} with IDS) -> {run_dir}; reported cost ${total_cost:.2f} "
          f"(Claude Code's estimate; the subscription is what pays)")


if __name__ == "__main__":
    main()
