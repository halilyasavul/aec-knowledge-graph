"""Shared paths and helpers for the NL->IDS evaluation loop."""
from __future__ import annotations

import json
import re
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
TESTSET_DIR = EVAL_DIR / "nl_to_ids_testset"
SPEC_TASKS = TESTSET_DIR / "spec_tasks.jsonl"
RUNS_DIR = EVAL_DIR / "runs"

# The only three values the IDS 1.0 XSD accepts in ifcVersion.
XSD_IFC_VERSIONS = {"IFC2X3", "IFC4", "IFC4X3_ADD2"}


def load_tasks(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def safe_name(item_id: str) -> str:
    """Filesystem-safe name for an item id ('#', '/', '\\' and friends)."""
    return re.sub(r"[#/\\:*?\"<>| ]", "_", item_id.replace("#", "__"))
