"""The official IDS audit (buildingSMART's ids-tool) on every Ishigaki gold and generated file.

    dotnet tool install -g ids-tool.commandline       # once; provides `ids-tool`
    python -m eval.ishigaki_bench.audit

Read-only apart from its outputs. Each file is audited twice: the full audit (IDS structure and
the "agreed limitation of IDS contents" -- the paper's "Content" column) and the structure
audit alone (`-c`). The gold files are audited too, as a check on the tool: the benchmark says
they were validated with it. Writes eval/reports/v9/h7_ishigaki_audit.csv (one row per file)
and h7_ishigaki_audit_summary.csv (pass rates per model and stage), and prints the error codes.

    python -m eval.ishigaki_bench.audit --suffix=-reserialized

audits the eval.ishigaki_bench.reserialize copies instead (<run>-reserialized; gold skipped) and
writes h7_ishigaki_audit_reserialized*.csv.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from eval.common import EVAL_DIR, RUNS_DIR, safe_name
from eval.ishigaki_bench.analysis import GROUPS, TASKS

OUT = EVAL_DIR / "reports" / "v9"
_STATUS = re.compile(r"Completed with status: (\w+)")
_ERROR = re.compile(r"Error (\d+): (.*)")


def ids_tool() -> str:
    exe = shutil.which("ids-tool") or str(Path(os.environ.get("USERPROFILE", "~")) / ".dotnet" / "tools" / "ids-tool.exe")
    if not Path(exe).exists():
        raise SystemExit("ids-tool not found; install it with `dotnet tool install -g ids-tool.commandline`")
    return exe


def audit(exe: str, path: Path, content: bool) -> dict:
    cmd = [exe, "audit", str(path)] + ([] if content else ["-c"])
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    out = p.stdout + p.stderr
    m = _STATUS.search(out)
    errors = [(int(c), msg) for c, msg in _ERROR.findall(out)]
    return {"status": m.group(1) if m else f"rc={p.returncode}", "rc": p.returncode,
            "codes": sorted({c for c, _ in errors}), "first_error": errors[0][1][:200] if errors else ""}


def main(argv=None):
    ap = argparse.ArgumentParser(description="official IDS audit of the Ishigaki files")
    ap.add_argument("--suffix", default="", help="audit eval/runs/<run><suffix>/generated instead (gold skipped)")
    args = ap.parse_args(argv)
    tag = "_" + args.suffix.strip("-_").replace("-", "_") if args.suffix else ""
    exe = ids_tool()
    tasks = {json.loads(l)["id"]: json.loads(l) for l in open(TASKS, encoding="utf-8")}
    stage_of = {}
    for name in ("native_41", "stage2_single_turn_20"):
        for i in json.loads((EVAL_DIR / "ishigaki_bench" / "item_lists" / f"{name}.json").read_text()):
            stage_of[i] = "stage 1" if name.startswith("native") else "stage 2"
    jobs = []
    gold_dir = Path(tempfile.mkdtemp(prefix="ishigaki-gold-"))
    for iid, it in tasks.items():
        if iid in stage_of and not args.suffix:
            p = gold_dir / f"{safe_name(iid)}.ids"
            p.write_text(it["gold_ids"], encoding="utf-8")
            jobs.append(("gold", stage_of[iid], "(gold)", iid, p))
    for model, stages in GROUPS.items():
        for stage, runs in stages.items():
            for run in runs:
                for iid in [i for i, s in stage_of.items() if s == stage]:
                    p = RUNS_DIR / (run + args.suffix) / "generated" / f"{safe_name(iid)}.ids"
                    if p.exists():
                        jobs.append((model, stage, run, iid, p))

    def one(job):
        model, stage, run, iid, p = job
        full, struct = audit(exe, p, True), audit(exe, p, False)
        return {"model": model, "stage": stage, "run": run, "id": iid,
                "input_format": tasks[iid]["input_format"],
                "full_status": full["status"], "full_pass": full["rc"] == 0, "full_codes": " ".join(map(str, full["codes"])),
                "full_first_error": full["first_error"],
                "structure_status": struct["status"], "structure_pass": struct["rc"] == 0,
                "structure_codes": " ".join(map(str, struct["codes"]))}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, jobs))
    shutil.rmtree(gold_dir, ignore_errors=True)
    d = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / f"h7_ishigaki_audit{tag}.csv", index=False)
    summary = (d.groupby(["model", "stage"], sort=False)
                 .agg(files=("id", "count"), full_audit_pass=("full_pass", "sum"),
                      structure_audit_pass=("structure_pass", "sum"))
                 .reset_index())
    summary["full_audit_rate"] = (summary.full_audit_pass / summary.files).round(4)
    summary["structure_audit_rate"] = (summary.structure_audit_pass / summary.files).round(4)
    summary.to_csv(OUT / f"h7_ishigaki_audit{tag}_summary.csv", index=False)
    print(summary.to_string(index=False))
    for (model, stage), g in d.groupby(["model", "stage"], sort=False):
        codes = Counter(c for cs in g.full_codes for c in cs.split())
        print(f"{model} {stage}: files failing per error code {dict(codes.most_common())}")
    print(f"-> {OUT / f'h7_ishigaki_audit{tag}.csv'}")


if __name__ == "__main__":
    main()
