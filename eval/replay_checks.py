"""Replay the v9 request checks over the generate_ids calls recorded in earlier runs.

    python -m eval.replay_checks [run ...]

No model calls. For every item-run, the request text is the prompt that was sent, the known
property sets are the query_class results logged before each generate_ids call, and the
document is the JSON the model sent. Reports which checks would have fired on the call that
the run accepted (the last successful one), and on every call. Writes
eval/reports/v9/e4_replay_checks.csv and prints a summary.
"""
from __future__ import annotations

import collections
import json
import sys

import pandas as pd

import aec_kg.ids.request_checks as rc
from aec_kg.ids.models import IdsDocument
from aec_kg.ids.request_checks import RequestContext, check_document
from eval.common import EVAL_DIR, RUNS_DIR

OUT = EVAL_DIR / "reports" / "v9"
DEFAULT_RUNS = ["run5-rep1", "run5-rep2", "run5-rep3", "run6-flash-rep1", "run6-flash-rep2"]
V = "Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids"


def _doc(args):
    raw = args.get("ids_json_string") or args.get("ids_json")
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw


def replay(run: str) -> list[dict]:
    rows = []
    for line in open(RUNS_DIR / run / "log.jsonl", encoding="utf-8"):
        rec = json.loads(line)
        ctx = RequestContext(request_text=rec.get("prompt_sent") or "")
        calls = rec.get("tool_calls") or []
        gen_calls = [(i, tc) for i, tc in enumerate(calls) if tc["tool"] == "generate_ids"]
        accepted = None
        for i, tc in gen_calls:
            if isinstance(tc.get("result"), dict) and tc["result"].get("success"):
                accepted = i
        for i, tc in enumerate(calls):
            if tc["tool"] == "query_class" and isinstance(tc.get("result"), dict):
                ctx.learn(tc["result"])
            if tc["tool"] != "generate_ids":
                continue
            try:
                doc = IdsDocument.model_validate(_doc(tc["args"]))
            except Exception as e:                       # the run itself rejected this call
                rows.append({"run": run, "id": rec["id"], "call": i, "accepted": i == accepted,
                             "pydantic_ok": False, "n_problems": None, "kinds": "", "problems": str(e)[:200]})
                continue
            rc.GUARDS.clear()
            problems = check_document(doc, ctx)
            rows.append({"run": run, "id": rec["id"], "call": i, "accepted": i == accepted,
                         "pydantic_ok": True, "n_problems": len(problems),
                         "kinds": " ".join(sorted(rc.GUARDS)), "problems": " || ".join(problems)[:1500]})
    return rows


def main(argv=None):
    runs = (argv if argv is not None else sys.argv[1:]) or DEFAULT_RUNS
    rows = []
    for r in runs:
        rows += replay(r)
    d = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "e4_replay_checks.csv", index=False)
    acc = d[d.accepted & d.pydantic_ok]
    print(f"{len(d)} generate_ids calls replayed, {len(acc)} of them the accepted document of an item-run")
    for grp, sub in acc.groupby(acc.run.str[:4]):
        fired = sub[sub.n_problems > 0]
        print(f"\n{grp}: checks fire on {len(fired)}/{len(sub)} accepted documents")
        kinds = collections.Counter(k for ks in fired.kinds for k in ks.split())
        for k, n in kinds.most_common():
            print(f"   {k:<40} {n}")
    # against the behavioural verdict the run actually got (determined-only, extras excused, probes)
    rows = []
    for run, sub in acc.groupby("run"):
        f = RUNS_DIR / run / "scores_relaxed_excused_probe.csv"
        if not f.exists():
            continue
        sc = pd.read_csv(f).set_index("id")
        for _, r in sub.iterrows():
            if r["id"] in sc.index:
                v = sc.loc[r["id"], "wit_outcome_equiv"]
                rows.append({"run": run, "id": r["id"], "checks_fire": bool(r["n_problems"] > 0), "kinds": r["kinds"],
                             "verdict": "unverified" if pd.isna(v) else ("exact" if v == 1 else "failing"),
                             "direction": sc.loc[r["id"], "wit_direction"]})
    if rows:
        j = pd.DataFrame(rows)
        j.to_csv(OUT / "e5_replay_vs_verdict.csv", index=False)
        j["group"] = j.run.str[:4]
        print("\nchecks firing x behavioural verdict (determined-only, extras excused, probe set):")
        print(pd.crosstab([j.group, j.checks_fire], j.verdict))
    print("\nper item (accepted documents with a finding):")
    for (iid, run), sub in acc[acc.n_problems > 0].groupby(["id", "run"]):
        print(f"  {run:<16} {iid.replace(V, 'Vienna'):<45} {sub.kinds.iloc[0]}")


if __name__ == "__main__":
    main()
