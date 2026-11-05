"""The request checks on held-out requests: when did they fire, and were they right?

    python -m eval.ishigaki_bench.check_firings

Read-only. For every Ishigaki item-run whose generate_ids calls returned `request_errors`, each
property a check named is looked up in the gold: if the gold puts a value constraint on it, the
check rejected something the request does determine (a false positive against the gold). The
final file is then compared on that property: did the model drop or change the constraint?
Writes eval/reports/v9/h6_ishigaki_request_checks.csv.
"""
from __future__ import annotations

import json
import re
from collections import Counter

import pandas as pd

from eval import score as S
from eval.common import EVAL_DIR, RUNS_DIR, safe_name
from eval.ishigaki_bench.analysis import GROUPS, TASKS

OUT = EVAL_DIR / "reports" / "v9"
_NAMED = re.compile(r"\]: (?:<pattern>|[^ ]+?)\.(.+?) (?:is pinned|minInclusive=|maxInclusive=|minExclusive=|"
                    r"maxExclusive=|= '|enumeration contains|lists \d)")


def kind(m: str) -> str:
    if "is pinned" in m:
        return "boolean_pin"
    if "states no such number" in m:
        return "bound"
    if "subset" in m or "lists " in m:
        return "enum_subset"
    return "value_not_in_request"


def main():
    tasks = {json.loads(l)["id"]: json.loads(l) for l in open(TASKS, encoding="utf-8")}
    rows = []
    for model, stages in GROUPS.items():
        for stage, runs in stages.items():
            for run in runs:
                log, sc = RUNS_DIR / run / "log.jsonl", RUNS_DIR / run / "scores_probe.csv"
                if not log.exists() or not sc.exists():
                    continue
                verdict = pd.read_csv(sc).set_index("id").wit_outcome_equiv
                for line in open(log, encoding="utf-8"):
                    r = json.loads(line)
                    msgs = [m for c in r["tool_calls"] if c["tool"] == "generate_ids" and isinstance(c["result"], dict)
                            for m in (c["result"].get("request_errors") or [])]
                    if not msgs:
                        continue
                    gold = {f.get("baseName"): f for f in tasks[r["id"]]["target"] if f["facet"] == "property"}
                    p = RUNS_DIR / run / "generated" / f"{safe_name(r['id'])}.ids"
                    final = {f.get("baseName"): f for f in (S.parse_candidate(p)["requirements"] if p.exists() else [])
                             if f["facet"] == "property"}
                    for m in msgs:
                        mm = _NAMED.search(m)
                        name = mm.group(1) if mm else None
                        g = gold.get(name)
                        f = final.get(name)
                        v = verdict.get(r["id"])
                        rows.append({"model": model, "stage": stage, "run": run, "id": r["id"], "check": kind(m),
                                     "property": name,
                                     "gold_value": (g or {}).get("value"), "final_value": (f or {}).get("value"),
                                     "gold_constrains": bool(g and g.get("value")),
                                     "final_matches_gold": bool(g and f and S.canon_value("property", "value", g.get("value"))
                                                                == S.canon_value("property", "value", f.get("value"))),
                                     "verdict": "unverified" if pd.isna(v) else ("exact" if v == 1 else "failing"),
                                     "message": m[:300]})
    d = pd.DataFrame(rows).drop_duplicates(subset=["run", "id", "check", "property"])
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "h6_ishigaki_request_checks.csv", index=False)
    for (model, stage), g in d.groupby(["model", "stage"]):
        runs_ = g.drop_duplicates(["run", "id"])
        print(f"{model} {stage}: checks fired in {len(runs_)} item-runs ({dict(Counter(g.check))}); "
              f"named a property the gold constrains: {int(g.gold_constrains.sum())}/{len(g)}; "
              f"final file then differs from gold there: {int((g.gold_constrains & ~g.final_matches_gold).sum())}; "
              f"item-runs ending exact/failing/unverified: {dict(Counter(runs_.verdict))}")
    print(f"-> {OUT / 'h6_ishigaki_request_checks.csv'}")


if __name__ == "__main__":
    main()
