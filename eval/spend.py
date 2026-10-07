"""Account for what the eval runs spent, from the run logs (work order v8 §1).

    python -m eval.spend [--csv eval/reports/v7/t6_spend.csv]

Read-only. Every figure comes from eval/runs/*/log.jsonl, which records one entry per item
with every model call, its token counts (input / output / thinking) and the derived cost.
Thinking tokens bill as output, so they are shown separately as a share of output cost.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from eval.common import RUNS_DIR

PRICE_IN_PER_M = 0.30          # gemini-2.5-flash list price used by eval/generate.py
PRICE_OUT_PER_M = 2.50


def run_rows() -> pd.DataFrame:
    rows = []
    for log in sorted(RUNS_DIR.glob("*/log.jsonl")):
        items = [json.loads(l) for l in open(log, encoding="utf-8")]
        if not items:
            continue
        calls = sum(len(i.get("llm_calls") or []) for i in items)
        think = sum(i.get("thinking_tokens") or 0 for i in items)
        tin = sum(i.get("input_tokens") or 0 for i in items)
        tout = sum(i.get("output_tokens") or 0 for i in items)
        cost = sum(i.get("cost_usd") or 0 for i in items)
        meta_path = log.parent / "run.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        rows.append({
            "run": log.parent.name,
            "model": meta.get("model", "?"),
            "created": meta.get("created", "?"),
            "n_items": len(items),
            "model_calls": calls,
            "calls_per_item": round(calls / len(items), 2),
            "input_tokens": tin,
            "output_tokens": tout,          # includes thinking, as billed
            "thinking_tokens": think,
            "thinking_share_of_output": round(think / tout, 3) if tout else None,
            "cost_usd": round(cost, 4),
            "cost_per_item": round(cost / len(items), 4),
            "thinking_cost_usd": round(think / 1e6 * PRICE_OUT_PER_M, 4),
        })
    return pd.DataFrame(rows).sort_values("created")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=None)
    a = ap.parse_args(argv)
    df = run_rows()
    cols = ["run", "model", "n_items", "model_calls", "calls_per_item", "input_tokens",
            "output_tokens", "thinking_tokens", "cost_usd", "cost_per_item"]
    print(df[cols].to_string(index=False))
    tot_cost = df.cost_usd.sum()
    tot_think = df.thinking_cost_usd.sum()
    print(f"\ntotal across {len(df)} runs: {df.n_items.sum()} items, {df.model_calls.sum()} model calls, "
          f"${tot_cost:.2f}")
    print(f"  input {df.input_tokens.sum():,} tok  output {df.output_tokens.sum():,} tok "
          f"(of which thinking {df.thinking_tokens.sum():,}, {100 * df.thinking_tokens.sum() / max(df.output_tokens.sum(), 1):.0f}%)")
    print(f"  thinking tokens alone account for ~${tot_think:.2f} at 2.5-Flash prices "
          f"(~{100 * tot_think / max(tot_cost, 1e-9):.0f}% of logged spend)")
    print(f"  indicative split at 2.5-Flash list prices: input ${df.input_tokens.sum() / 1e6 * PRICE_IN_PER_M:.2f} | "
          f"output ${df.output_tokens.sum() / 1e6 * PRICE_OUT_PER_M:.2f}")
    print("  (cost_usd per run already uses that run's own model prices; the split above is "
          "indicative only, since runs used different models)")
    if a.csv:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(a.csv, index=False)
        print(f"-> {a.csv}")


if __name__ == "__main__":
    main()
