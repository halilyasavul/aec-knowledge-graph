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
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        sys.exit(__doc__)
    runs = [Path(a) for a in argv]
    ids: list[str] = []
    for r in runs:
        for line in open(r / "log.jsonl", encoding="utf-8"):
            i = json.loads(line)["id"]
            if i not in ids:
                ids.append(i)
    identical = same_status = 0
    print(f"{len(runs)} runs, {len(ids)} items, normalised comparison")
    for i in ids:
        sigs = [signature(r / "generated" / f"{safe_name(i)}.ids") for r in runs]
        present = [s is not None for s in sigs]
        uniq = len(set(sigs))
        same_status += int(len(set(present)) == 1)
        identical += int(uniq == 1 and all(present))
        mark = "same" if uniq == 1 and all(present) else f"{uniq} variants"
        print(f"  {i[-40:]:<42} {mark:<12} files: {sum(present)}/{len(runs)}")
    print(f"\nidentical after normalisation: {identical}/{len(ids)} "
          f"({100 * identical / len(ids):.0f}%)   same produced/not-produced outcome: {same_status}/{len(ids)}")
    if identical < len(ids):
        print("temperature 0 is not a guarantee: tool-call order and retries still vary the input")


if __name__ == "__main__":
    main()
