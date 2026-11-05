"""Rebuild every ignored usBridge file from the sources, in order.

    python -X utf8 -m eval.usbridge.build              # bSDD cache -> reference -> workbook -> IDM -> alignment
                                                       # -> items -> determinacy
    python -X utf8 -m eval.usbridge.build --kg         # + load usBridge into the local Neo4j and coverage
    python -X utf8 -m eval.usbridge.build --harness    # + reference-vs-reference scoring

Needs eval/usbridge/source/ (see SOURCES.md; not committed). The bSDD cache is fetched only for
what is missing. --kg needs NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD for the local eval container.

Committed: the scripts, SOURCES.md, alignment.csv, reference/corrections.json, summary/*.json and
the reports. Ignored (rebuilt here): source/, bsdd/, reference/* (but corrections.json), idm/,
items.jsonl, annotations/, eval/runs/.
"""
from __future__ import annotations

import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    from eval.usbridge import align, bsdd, determinacy, idm, items, reference, workbook
    steps = [("bSDD cache", lambda: bsdd.main([])),
             ("reference", reference.main),
             ("workbook", workbook.main),
             ("IDM-1 Section 4", idm.main),
             ("alignment", align.main),
             ("items", items.main),
             ("determinacy", determinacy.main)]
    if "--kg" in argv:
        from eval.usbridge import kg
        steps += [("KG load", kg.load), ("KG coverage", kg.coverage)]
    if "--harness" in argv:
        from eval.usbridge import harness_check
        steps.append(("harness", lambda: harness_check.main([])))
    for name, fn in steps:
        print(f"\n=== {name}", flush=True)
        fn()


if __name__ == "__main__":
    main()
