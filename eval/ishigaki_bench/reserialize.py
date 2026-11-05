"""Re-serialize the documents the Ishigaki runs generated, with the current serializer. No model calls.

    python -m eval.ishigaki_bench.reserialize

For every run in analysis.GROUPS, the JSON of each item's accepted generate_ids call (in
log.jsonl) is validated and serialized again into eval/runs/<run>-reserialized/generated/; the
run directory itself is untouched. Used to measure what the two serializer defaults changed in
handover 2 (applicability minOccurs/maxOccurs, restriction base from the dataType) cost in the
official audit: the model's output is the same, only its rendering differs. Each new file is
checked against the original with those attributes stripped -- they must be identical.
"""
from __future__ import annotations

import json
import shutil

from lxml import etree

from aec_kg.ids.models import IdsDocument
from aec_kg.ids.serializer import serialize_ids
from eval.common import RUNS_DIR, safe_name
from eval.ishigaki_bench.analysis import GROUPS

SUFFIX = "-reserialized"


def _without_defaults(xml: bytes) -> bytes:
    """The document with the two attributes the serializer change touches removed."""
    root = etree.fromstring(xml)
    for app in root.iter("{*}applicability"):
        app.attrib.pop("minOccurs", None)
        app.attrib.pop("maxOccurs", None)
    for r in root.iter("{http://www.w3.org/2001/XMLSchema}restriction"):
        r.attrib.pop("base", None)
    return etree.tostring(root, method="c14n")


def accepted_document(rec: dict) -> dict | None:
    calls = [c for c in rec.get("tool_calls") or [] if c["tool"] == "generate_ids"
             and isinstance(c.get("result"), dict) and c["result"].get("success")]
    if not calls:
        return None
    raw = calls[-1]["args"].get("ids")
    return json.loads(raw) if isinstance(raw, str) else raw


def main():
    for model, stages in GROUPS.items():
        for stage, runs in stages.items():
            for run in runs:
                src = RUNS_DIR / run
                if not (src / "log.jsonl").exists():
                    continue
                dst = RUNS_DIR / (run + SUFFIX)
                (dst / "generated").mkdir(parents=True, exist_ok=True)
                shutil.copy(src / "log.jsonl", dst / "log.jsonl")
                n = same = 0
                differs = []
                for line in open(src / "log.jsonl", encoding="utf-8"):
                    rec = json.loads(line)
                    doc = accepted_document(rec)
                    if doc is None:
                        continue
                    name = safe_name(rec["id"])
                    xml = serialize_ids(IdsDocument.model_validate(doc))
                    (dst / "generated" / f"{name}.ids").write_text(xml, encoding="utf-8")
                    n += 1
                    orig = (src / "generated" / f"{name}.ids").read_bytes()
                    if _without_defaults(orig) == _without_defaults(xml.encode("utf-8")):
                        same += 1
                    else:
                        differs.append(rec["id"])
                (dst / "reserialized_from.json").write_text(json.dumps({"source_run": run, "files": n}, indent=1))
                print(f"{model:<44} {stage}: {n} documents re-serialized -> {dst.name}; identical to the original "
                      f"apart from occurs/base: {same}/{n}" + (f"; differ: {differs}" if differs else ""))


if __name__ == "__main__":
    main()
