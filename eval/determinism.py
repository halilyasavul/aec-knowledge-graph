"""Compare repeat runs of the same items: how often is the generated IDS the same?

    python -m eval.determinism <run_dir> <run_dir> [<run_dir> ...]

Comparison is after normalisation, not byte-for-byte: the canonical facet multiset,
applicability and ifcVersion. Titles, element order and whitespace do not count, because
they do not change what the specification checks.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from eval import score
from eval.common import safe_name


def signature(path: Path) -> str | None:
    if not path.exists():
        return None
    c = score.parse_candidate(path)
    reqs = sorted(str(score.canon(f)) for f in c["requirements"])
    apps = sorted(str(score.canon(a)) for a in c["applicability"])
    return json.dumps({"requirements": reqs, "applicability": apps,
                       "ifcVersion": sorted(c["versions"]), "n_specs": c["n_specs"]}, sort_keys=True)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("-o", "--out", help="also write the result as JSON")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    runs = [Path(r) for r in a.runs]
    ids: list[str] = []
    for r in runs:
        for line in open(r / "log.jsonl", encoding="utf-8"):
            i = json.loads(line)["id"]
            if i not in ids:
                ids.append(i)
    identical = same_status = 0
    per_item = []
    print(f"{len(runs)} runs, {len(ids)} items, normalised comparison")
    for i in ids:
        sigs = [signature(r / "generated" / f"{safe_name(i)}.ids") for r in runs]
        present = [s is not None for s in sigs]
        uniq = len(set(sigs))
        same_status += int(len(set(present)) == 1)
        identical += int(uniq == 1 and all(present))
        mark = "same" if uniq == 1 and all(present) else f"{uniq} variants"
        per_item.append({"id": i, "variants": uniq, "files": sum(present), "runs": len(runs)})
        print(f"  {i[-40:]:<42} {mark:<12} files: {sum(present)}/{len(runs)}")
    print(f"\nidentical after normalisation: {identical}/{len(ids)} "
          f"({100 * identical / len(ids):.0f}%)   same produced/not-produced outcome: {same_status}/{len(ids)}")
    if identical < len(ids):
        print("temperature 0 is not a guarantee: tool-call order and retries still vary the input")
    if a.out:
        Path(a.out).write_text(json.dumps(
            {"runs": [r.name for r in runs], "items": len(ids), "identical": identical,
             "same_status": same_status, "per_item": per_item}, indent=1), encoding="utf-8")
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
