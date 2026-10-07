"""Measure what compact tool results would save, from logs only — no model calls (v8).

    python -m eval.compact_probe run6-flash-pilot

For every logged tool result, compare the characters delivered today with what
`compact_class_result` would deliver. A result sent at call k is resent in every later call of
the same item, so the saving compounds; the token estimate below accounts for that and is
labelled an estimate (4 characters per token, the usual rule of thumb for JSON).
"""
from __future__ import annotations

import argparse
import json

from aec_kg.main_orchestrator import compact_class_result, maybe_truncate
from eval.common import RUNS_DIR

CHARS_PER_TOKEN = 4


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run")
    a = ap.parse_args(argv)
    rows = []
    for line in open(RUNS_DIR / a.run / "log.jsonl", encoding="utf-8"):
        j = json.loads(line)
        calls = len(j.get("llm_calls") or [])
        tool_calls = j.get("tool_calls") or []
        item_now = item_compact = 0
        for i, c in enumerate(tool_calls):
            res = c.get("result") or {}
            if "property_sets" not in res:
                continue
            now = len(json.dumps(maybe_truncate(res), default=str, ensure_ascii=False))
            comp = len(json.dumps(compact_class_result(res), default=str, ensure_ascii=False))
            resends = max(calls - i, 1)            # delivered once, then carried in later calls
            item_now += now * resends
            item_compact += comp * resends
        if item_now:
            rows.append({"id": j["id"], "llm_calls": calls, "class_lookups": sum(
                1 for c in tool_calls if "property_sets" in (c.get("result") or {})),
                "chars_now_incl_resends": item_now, "chars_compact_incl_resends": item_compact,
                "input_tokens_logged": j["input_tokens"],
                "est_tokens_saved": int((item_now - item_compact) / CHARS_PER_TOKEN)})
    if not rows:
        print("no class lookups in that run's log")
        return
    tot_now = sum(r["chars_now_incl_resends"] for r in rows)
    tot_comp = sum(r["chars_compact_incl_resends"] for r in rows)
    tot_in = sum(r["input_tokens_logged"] for r in rows)
    saved = sum(r["est_tokens_saved"] for r in rows)
    print(f"run {a.run}: {len(rows)} items with class lookups")
    for r in rows:
        print(f"  {r['id'][-34:]:<36} lookups {r['class_lookups']}  calls {r['llm_calls']}  "
              f"tool chars {r['chars_now_incl_resends']:>9,} -> {r['chars_compact_incl_resends']:>8,}  "
              f"est. tokens saved {r['est_tokens_saved']:>7,} of {r['input_tokens_logged']:>7,} logged")
    print(f"\ntool-result characters (counting resends): {tot_now:,} -> {tot_comp:,} "
          f"({100 * (1 - tot_comp / tot_now):.0f}% smaller)")
    print(f"estimated input-token saving: {saved:,} of {tot_in:,} logged input tokens "
          f"({100 * saved / tot_in:.0f}%)")
    print("Prose (definitions, descriptions) is what gets dropped; every property-set name, "
          "property name, IFC type and allowed-value list is kept.")
    print("NOTE: estimate only. It was not used for any run; measuring it for real needs a run.")


if __name__ == "__main__":
    main()
