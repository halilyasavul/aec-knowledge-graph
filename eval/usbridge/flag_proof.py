"""Proof of the server flag: the real ifc MCP server over stdio, once per condition, one
search_classes call each, against the local graph.

    python -X utf8 -m eval.usbridge.flag_proof [term]      # default term: "Pier"

Needs NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD (local eval container). Writes
eval/usbridge/summary/flag_proof.json.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent


async def call(dictionaries: str, term: str) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8"}
    args = ["-m", "aec_kg.mcp_server"] + ([] if dictionaries == "ifc" else ["--dictionaries", dictionaries])
    async with stdio_client(StdioServerParameters(command=sys.executable, args=args, env=env)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("search_classes", {"term": term})
            payload = getattr(res, "structured_content", None) or json.loads(res.content[0].text)
            rows = payload.get("result", payload)
            return {"server_args": args[2:], "term": term, "n": len(rows),
                    "by_dictionary": {d: sum(1 for x in rows if x.get("dictionary", "(none)") == d)
                                      for d in sorted({x.get("dictionary", "(none)") for x in rows})},
                    # codes and names only: the definitions quote bSDD (usBridge is rights-reserved)
                    "rows": [{k: x[k] for k in ("code", "name", "dictionary", "ifc_entity", "predefinedType",
                                                "objectType") if k in x} for x in rows]}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    term = argv[0] if argv else "Pier"
    out = {c: asyncio.run(call(c, term)) for c in ("ifc", "ifc,usbridge")}
    (ROOT / "summary").mkdir(exist_ok=True)
    (ROOT / "summary" / "flag_proof.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for c, r in out.items():
        print(f"--dictionaries {c}: search_classes({term!r}) -> {r['n']} rows {r['by_dictionary']}")
        for x in r["rows"][:12]:
            print("   ", {k: x[k] for k in ("code", "name", "dictionary", "ifc_entity", "predefinedType") if k in x})


if __name__ == "__main__":
    main()
