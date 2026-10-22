"""Step 2 — run each task prompt through the shipped generation path and save the IDS.

    python -m eval.generate [--limit N] [--run-id ID] [--tasks PATH]

Calls ``aec_kg.main_orchestrator.run_agent`` unchanged (same system prompt, tools,
agent loop). The only thing added is instrumentation wrapped around two module
functions — ``_call_with_retry`` (tokens, model version, latency) and
``dispatch_tool`` (every tool call and its full result) — plus strict XSD validation.

Only ``item["prompt"]`` reaches the model. The user turn is a fixed, logged rendering
of that dict (see ``build_message``); ``assert_no_leak`` checks it on every item.

Resumable: an item is skipped when ``generated/<name>.ids`` or ``generated/<name>.fail.json``
exists. Infrastructure errors (API/DB exceptions) write neither, so they retry on resume.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from eval.common import RUNS_DIR, SPEC_TASKS, graph_psets, ifc_only, load_tasks, safe_name

# --------------------------------------------------------------------------- model pin
# The Gemini Developer API exposes no suffix more specific than this code: the
# "-001" form 404s. We pin by asserting that the API reports this exact version at
# start-up and that every response's model_version matches — the run aborts
# rather than silently mixing model versions.
PINNED_MODEL = "gemini-2.5-flash"
PINNED_MODEL_VERSION = "001"
# USD per 1M tokens, Gemini API paid tier list price for gemini-2.5-flash (text).
# Thinking tokens bill as output.
PRICE_IN_PER_M = 0.30
PRICE_OUT_PER_M = 2.50

ALLOWED_PROMPT_KEYS = {"applies_to", "requirements"}

# The schema of the models every candidate is executed against. Stated in the request because
# 19% of v5 behavioural failures were specs whose declared ifcVersion excluded the test model —
# a question about the delivery context, not about the requirements. It is the same constant for
# every item, so it carries no information about any individual item's answer.
TARGET_SCHEMA = "IFC4X3_ADD2"


class PinViolation(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    """One item used more than its share; it is abandoned, not retried."""


class RunAborted(RuntimeError):
    """Stop the whole run: credit exhausted, repeated server errors, or the spend cap."""


# Cost controls (work order v8 §2). Run 5 median was 89k tokens per item, so 3x is 267k.
TOKEN_CEILING_PER_ITEM = 267_000
MAX_CALLS_PER_ITEM = 10            # same bound as the agent loop's MAX_ITERATIONS
MAX_CONSECUTIVE_5XX = 3
SERVED_VERSION: str | None = None   # the exact version string the API served first, pinned per run


# --------------------------------------------------------------------------- prompt
def build_message(prompt: dict) -> str:
    """Render the task prompt as the user turn. A pure function of ``prompt`` only."""
    assert set(prompt) == ALLOWED_PROMPT_KEYS, f"unexpected prompt keys: {sorted(prompt)}"
    app = prompt["applies_to"] or {}
    target = app.get("entity", "")
    if app.get("predefinedType"):
        target += f" (predefined type: {app['predefinedType']})"
    lines = ["Generate an IDS specification.", f"Target schema: {TARGET_SCHEMA}",
             f"Applies to: {target}", "Requirements:"]
    lines += [f"{i}. {r}" for i, r in enumerate(prompt["requirements"], 1)]
    return "\n".join(lines)


def _target_names(item: dict) -> list[str]:
    # same rule extract_testset.py uses to set `leak`
    out = []
    for t in item.get("target", []):
        for k in ("propertySet", "baseName", "name", "system"):
            v = t.get(k)
            if v and not str(v).startswith("RESTRICTION("):
                out.append(str(v))
    return out


def assert_no_leak(item: dict, message: str) -> None:
    """Fail loudly if anything but item['prompt'] could have reached the model."""
    prompt_json = json.dumps(item["prompt"], ensure_ascii=False)
    assert message == build_message(copy.deepcopy(item["prompt"])), "message is not a pure rendering of prompt"
    for key in ("source", "id"):
        assert item[key] not in message, f"{key} leaked into message"
    sn = item.get("spec_name") or ""
    if sn and sn not in prompt_json:
        assert sn not in message, "spec_name leaked into message"
    if not item.get("any_leak"):
        hits = [n for n in _target_names(item) if n in message and n not in prompt_json]
        assert not hits, f"target names leaked into message: {hits}"


# --------------------------------------------------------------------------- instrumentation
class Recorder:
    def __init__(self, temperature: float | None = None):
        self.temperature = temperature
        self.run_cost = 0.0            # cumulative over the whole run
        self.consecutive_5xx = 0
        self.reset()

    def reset(self):
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self.api_retries = 0
        self.empty_retries = 0
        self.guards_before = None
        self.item_tokens = 0


class _RetryCounter(logging.Handler):
    def __init__(self, rec: Recorder):
        super().__init__(logging.WARNING)
        self.rec = rec

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith("Rate limited"):
            self.rec.api_retries += 1
        elif msg.startswith("Empty response") and "after retry" not in msg:
            self.rec.empty_retries += 1


def instrument(mo, rec: Recorder) -> None:
    orig_call, orig_dispatch = mo._call_with_retry, mo.dispatch_tool

    def call(client, model, contents, config):
        if model != PINNED_MODEL:
            raise PinViolation(f"orchestrator requested {model!r}, pinned {PINNED_MODEL!r}")
        if len(rec.llm_calls) >= MAX_CALLS_PER_ITEM:
            raise BudgetExceeded(f"item hit {MAX_CALLS_PER_ITEM} model calls")
        if rec.item_tokens > TOKEN_CEILING_PER_ITEM:
            raise BudgetExceeded(f"item used {rec.item_tokens:,} tokens (ceiling {TOKEN_CEILING_PER_ITEM:,})")
        if rec.temperature is not None and getattr(config, "temperature", None) != rec.temperature:
            config = config.model_copy(update={"temperature": rec.temperature})
        t0 = time.perf_counter()
        try:
            resp = orig_call(client, model, contents, config)
        except Exception as e:
            msg = str(e)
            if "402" in msg or "credits are depleted" in msg:
                raise RunAborted(f"credit depleted: {msg[:160]}") from e
            if any(c in msg for c in ("500", "502", "503", "504", "INTERNAL", "UNAVAILABLE")):
                rec.consecutive_5xx += 1
                if rec.consecutive_5xx >= MAX_CONSECUTIVE_5XX:
                    raise RunAborted(f"{rec.consecutive_5xx} consecutive server errors: {msg[:160]}") from e
            raise
        rec.consecutive_5xx = 0
        u = resp.usage_metadata
        mv = getattr(resp, "model_version", None)
        rec.llm_calls.append({
            "ms": round((time.perf_counter() - t0) * 1000),
            "model_version": mv,
            "finish_reason": str(getattr(resp.candidates[0], "finish_reason", None)) if resp.candidates else None,
            "prompt_tokens": getattr(u, "prompt_token_count", None) or 0,
            "output_tokens": getattr(u, "candidates_token_count", None) or 0,
            "thinking_tokens": getattr(u, "thoughts_token_count", None) or 0,
            "cached_tokens": getattr(u, "cached_content_token_count", None) or 0,
        })
        c = rec.llm_calls[-1]
        rec.item_tokens += c["prompt_tokens"] + c["output_tokens"] + c["thinking_tokens"]
        rec.run_cost += (c["prompt_tokens"] / 1e6 * PRICE_IN_PER_M
                         + (c["output_tokens"] + c["thinking_tokens"]) / 1e6 * PRICE_OUT_PER_M)
        global SERVED_VERSION
        if mv:
            if SERVED_VERSION is None:
                SERVED_VERSION = mv                  # pin whatever the API actually served
            elif mv != SERVED_VERSION:
                raise PinViolation(f"model_version changed mid-run: {SERVED_VERSION!r} -> {mv!r}")
        return resp

    def dispatch(name, args):
        t0 = time.perf_counter()
        result = orig_dispatch(name, args)
        size = len(json.dumps(result, default=str, ensure_ascii=False))
        delivered = mo.maybe_truncate(result)          # exactly what run_agent will send on
        dsize = len(json.dumps(delivered, default=str, ensure_ascii=False))
        sets_in = set((result or {}).get("property_sets") or {})
        sets_out = set((delivered or {}).get("property_sets") or {})
        rec.tool_calls.append({
            "tool": name, "args": args,
            "result": json.loads(json.dumps(result, default=str, ensure_ascii=False)),
            "ms": round((time.perf_counter() - t0) * 1000),
            "result_chars": size, "delivered_chars": dsize, "truncated_for_model": dsize < size,
            "property_sets_in": len(sets_in), "property_sets_delivered": len(sets_out),
            "property_sets_dropped": sorted(sets_in - sets_out),
            "truncation": (delivered or {}).get("_truncation"),
        })
        return result

    mo._call_with_retry = call
    mo.dispatch_tool = dispatch
    logging.getLogger(mo.__name__).addHandler(_RetryCounter(rec))


# --------------------------------------------------------------------------- run metadata
def _git():
    def g(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    return {"commit": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain", "--", "aec_kg"))}


def run_metadata(mo) -> dict:
    from urllib.parse import urlparse
    from google import genai
    from aec_kg import config as cfg

    client = genai.Client(api_key=cfg.GEMINI_API_KEY)   # keep a reference: a temporary client closes mid-request
    m = client.models.get(model=PINNED_MODEL)
    if PINNED_MODEL_VERSION and m.version != PINNED_MODEL_VERSION:
        raise PinViolation(f"API reports {PINNED_MODEL} version {m.version!r}, pinned {PINNED_MODEL_VERSION!r}")
    counts = mo._run_cypher_safe(
        "MATCH (c:Class) WITH count(c) AS classes "
        "MATCH (ps:PropertySet) WITH classes, count(ps) AS psets "
        "MATCH (p:Property) WITH classes, psets, count(p) AS props "
        "MATCH ()-[r:HAS_PROPERTY_SET]->() RETURN classes, psets, props, count(r) AS class_pset_rels")
    if "error" in counts or not counts.get("records") or not counts["records"][0]["classes"]:
        raise RuntimeError(f"knowledge graph unavailable or empty: {counts}")
    return {
        "model": PINNED_MODEL, "model_api_version": m.version,
        "price_in_per_m": PRICE_IN_PER_M, "price_out_per_m": PRICE_OUT_PER_M,
        "model_defaults": {"temperature": m.temperature, "top_p": m.top_p, "top_k": m.top_k,
                           "thinking": getattr(m, "thinking", None)},
        "price_usd_per_m": {"input": PRICE_IN_PER_M, "output": PRICE_OUT_PER_M},
        "system_prompt_sha256": hashlib.sha256(mo.SYSTEM_PROMPT.encode()).hexdigest(),
        "xsd_sha256": hashlib.sha256(Path(cfg.IDS_XSD_PATH).read_bytes()).hexdigest(),
        "neo4j_host": urlparse(cfg.NEO4J_URI).hostname,
        "graph_counts": counts["records"][0],
        "git": _git(), "python": sys.version.split()[0],
        "message_template": build_message({"applies_to": {"entity": "<ENTITY>", "predefinedType": "<TYPE>"},
                                           "requirements": ["<req 1>", "<req 2>"]}),
    }


# --------------------------------------------------------------------------- ordering
def ordered(tasks: list[dict]) -> list[dict]:
    """Round-robin across source files, so --limit is diverse."""
    def rr(items):
        by_src: dict[str, list] = {}
        for t in items:
            by_src.setdefault(t["source"], []).append(t)
        queues = [by_src[k] for k in sorted(by_src)]
        out = []
        while any(queues):
            for q in queues:
                if q:
                    out.append(q.pop(0))
        return out
    return rr(tasks)


# --------------------------------------------------------------------------- main
def main(argv=None):
    global PINNED_MODEL, PINNED_MODEL_VERSION, PRICE_IN_PER_M, PRICE_OUT_PER_M
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tasks", default=str(SPEC_TASKS))
    ap.add_argument("--run-id", default=f"spec_{PINNED_MODEL}")
    ap.add_argument("--all", action="store_true",
                    help="include items needing project-specific property sets (default: IFC-only items)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N items of the fixed order (completed ones count toward N)")
    ap.add_argument("--ids-file", help="JSON list of item ids to run (exactly those, in that order)")
    ap.add_argument("--temperature", type=float, default=0.0, help="0 for eval reproducibility (the app leaves it unset)")
    ap.add_argument("--no-truncation-fix", action="store_true", help="ablation: restore the pre-v5 tool-result trimming")
    ap.add_argument("--no-model-guards", action="store_true", help="ablation: restore lenient IDS models (unknown keys ignored)")
    ap.add_argument("--model", default=PINNED_MODEL, help="model id to generate with")
    ap.add_argument("--model-version", default=None,
                    help="expected API version string for --model; the run aborts if it differs")
    ap.add_argument("--price-in", type=float, default=PRICE_IN_PER_M,
                    help="USD per 1M input tokens for this model (cost figures use it)")
    ap.add_argument("--price-out", type=float, default=PRICE_OUT_PER_M,
                    help="USD per 1M output tokens, thinking included")
    ap.add_argument("--project-items", type=int, default=None,
                    help="item count to project the pilot cost onto (default: the run's own item list)")
    ap.add_argument("--pilot", type=int, default=0,
                    help="run N items, then report measured cost per item and the projection, and stop")
    ap.add_argument("--max-spend", type=float, default=None,
                    help="abort the run once cumulative spend reaches this (USD)")
    ap.add_argument("--no-datatype-fix", action="store_true",
                    help="ablation: hide the graph's ifc_type and restore the String->IFCTEXT mapping")
    ap.add_argument("--no-request-checks", action="store_true",
                    help="ablation: do not reject values/names the request does not support (v9)")
    args = ap.parse_args(argv)

    import aec_kg.ids.validator as validator
    validator.STRICT = True                       # a missing XSD must raise, never pass
    PINNED_MODEL = args.model
    PINNED_MODEL_VERSION = args.model_version if args.model_version else (
        PINNED_MODEL_VERSION if args.model == "gemini-2.5-flash" else None)
    PRICE_IN_PER_M, PRICE_OUT_PER_M = args.price_in, args.price_out
    import aec_kg.ids.models as ids_models
    import aec_kg.neuro_agent as neuro
    import aec_kg.main_orchestrator as mo
    logging.getLogger().setLevel(logging.WARNING)  # after aec_kg.config's basicConfig(INFO)
    mo.GEMINI_MODEL = PINNED_MODEL                # explicit, independent of .env
    if args.no_truncation_fix:
        mo.LEGACY_TRUNCATION = True               # v4 behaviour: whole property sets can vanish
    if args.no_model_guards:
        ids_models.set_guards(False)              # v4 behaviour: unknown keys silently ignored
    neuro.INCLUDE_IFC_TYPE = not args.no_datatype_fix
    mo.set_datatype_mode(not args.no_datatype_fix)
    import aec_kg.ids.request_checks as request_checks
    request_checks.set_request_checks(not args.no_request_checks)
    mo.set_request_rules(not args.no_request_checks)      # the prompt rules travel with the checks
    fixes = {"truncation_fix": not args.no_truncation_fix, "model_guards": not args.no_model_guards,
             "datatype_fix": not args.no_datatype_fix, "request_checks": not args.no_request_checks,
             "temperature": args.temperature, "max_tool_result_chars": mo.MAX_TOOL_RESULT_CHARS,
             "legacy_truncation": mo.LEGACY_TRUNCATION, "strict_xsd": True}

    run_dir = RUNS_DIR / args.run_id
    gen_dir = run_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)

    meta = run_metadata(mo)
    meta["fixes"] = fixes
    meta_path = run_dir / "run.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text())
        for k in ("model", "model_api_version", "system_prompt_sha256", "xsd_sha256", "graph_counts",
                  "message_template", "fixes"):
            if prev.get(k) != meta.get(k):
                sys.exit(f"refusing to resume {args.run_id}: {k} changed ({prev.get(k)!r} -> {meta.get(k)!r})")
    else:
        meta["tasks"] = str(Path(args.tasks).resolve())
        meta["created"] = dt.datetime.now().isoformat(timespec="seconds")
        meta_path.write_text(json.dumps(meta, indent=2, default=str))

    rec = Recorder(temperature=args.temperature)
    instrument(mo, rec)

    tasks = ordered(load_tasks(args.tasks))
    if args.ids_file:
        wanted = json.loads(Path(args.ids_file).read_text())
        by_id = {t["id"]: t for t in tasks}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            sys.exit(f"ids not found in tasks: {missing}")
        tasks = [by_id[i] for i in wanted]
        print(f"explicit id list: {len(tasks)} items")
    elif not args.all:
        psets = graph_psets(run_dir)
        if psets is None:
            sys.exit("graph needed to select IFC-only items (or pass --all)")
        tasks = [t for t in tasks if ifc_only(t, psets)]
        print(f"IFC-only items: {len(tasks)}")
    id_map_path = run_dir / "id_map.json"
    id_map = json.loads(id_map_path.read_text()) if id_map_path.exists() else {}
    log_path = run_dir / "log.jsonl"

    order = [t["id"] for t in tasks]
    (run_dir / "order.json").write_text(json.dumps(order, indent=0))
    todo = tasks[: args.limit] if args.limit else tasks
    done = ok = 0
    for item in todo:
        name = safe_name(item["id"])
        id_map[name] = item["id"]
        out_ids, out_fail = gen_dir / f"{name}.ids", gen_dir / f"{name}.fail.json"
        if out_ids.exists() or out_fail.exists():
            continue
        message = build_message(item["prompt"])
        assert_no_leak(item, message)

        rec.reset()
        guards0 = dict(ids_models.GUARDS)
        entry = {"id": item["id"], "file": name, "model": PINNED_MODEL, "model_api_version": PINNED_MODEL_VERSION,
                 "temperature": None, "prompt_sent": message, "prompt_chars": len(message),
                 "started": dt.datetime.now().isoformat(timespec="seconds")}
        t0 = time.perf_counter()
        error = answer = None
        budget_hit = False
        try:
            answer, _, _ = mo.run_agent(message)
        except BudgetExceeded as e:                  # abandon this item, never retry it
            error, budget_hit = f"BudgetExceeded: {e}", True
        except Exception as e:                       # infra failure: retry on resume
            error = f"{type(e).__name__}: {e}"
            if isinstance(e, (PinViolation, RunAborted)):
                raise
        entry["wall_ms"] = round((time.perf_counter() - t0) * 1000)

        gen_calls = [c for c in rec.tool_calls if c["tool"] == "generate_ids"]
        success = [c for c in gen_calls if c["result"].get("success")]
        tin = sum(c["prompt_tokens"] for c in rec.llm_calls)
        tout = sum(c["output_tokens"] + c["thinking_tokens"] for c in rec.llm_calls)
        entry.update({
            "temperature": rec.temperature,     # None = unset in shipped config -> API default (see run.json)
            "llm_calls": rec.llm_calls, "tool_calls": rec.tool_calls,
            "retries": {"api_rate_limit": rec.api_retries, "empty_response": rec.empty_retries,
                        "generate_ids_attempts": len(gen_calls),
                        "generate_ids_failures": len(gen_calls) - len(success)},
            "input_tokens": tin, "output_tokens": tout,
            "thinking_tokens": sum(c["thinking_tokens"] for c in rec.llm_calls),
            "cost_usd": round(tin / 1e6 * PRICE_IN_PER_M + tout / 1e6 * PRICE_OUT_PER_M, 6),
            "answer": answer,
            "guards_fired": {k: v - guards0.get(k, 0) for k, v in ids_models.GUARDS.items()
                             if v - guards0.get(k, 0)},
            "property_sets_dropped": sorted({ps for c in rec.tool_calls for ps in c.get("property_sets_dropped", [])}),
            "tool_result_chars_max": max((c["result_chars"] for c in rec.tool_calls), default=0),
        })
        if budget_hit:
            out_fail.write_text(json.dumps({"id": item["id"], "reason": error,
                                            "tokens": rec.item_tokens}, indent=1))
            entry.update(status="budget_exceeded", error=error,
                         output=str(out_fail.relative_to(run_dir)))
        elif error:
            entry.update(status="error", error=error)
        elif success:
            out_ids.write_text(success[-1]["result"]["ids_xml"], encoding="utf-8")
            entry.update(status="ok", output=str(out_ids.relative_to(run_dir)))
            ok += 1
        else:
            reason = (gen_calls[-1]["result"].get("error") if gen_calls else "generate_ids never called")
            out_fail.write_text(json.dumps({"id": item["id"], "reason": reason, "answer": answer}, indent=1))
            entry.update(status="no_file", error=reason, output=str(out_fail.relative_to(run_dir)))
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        id_map_path.write_text(json.dumps(id_map, indent=1))
        done += 1
        print(f"[{done}] {item['id']:<55} {entry['status']:<16} {entry['wall_ms']/1000:6.1f}s "
              f"tools={len(rec.tool_calls)} gen={len(gen_calls)} ${entry['cost_usd']:.4f} "
              f"run=${rec.run_cost:.2f}", flush=True)
        if args.max_spend and rec.run_cost >= args.max_spend:
            print(f"\nSTOPPING: run spend ${rec.run_cost:.2f} reached the cap ${args.max_spend:.2f} "
                  f"after {done} items. Resume with the same --run-id to continue.")
            break
        if args.pilot and done >= args.pilot:
            break

    id_map_path.write_text(json.dumps(id_map, indent=1))
    if mo._neo4j_driver is not None:
        mo._neo4j_driver.close()
    print(f"\n{done} generated this session ({ok} with IDS) -> {run_dir}")
    print(f"spend this session: ${rec.run_cost:.2f}")
    if args.pilot and done:
        per_item = rec.run_cost / done
        full = args.project_items or len(tasks)
        print(f"\nPILOT RESULT  model {PINNED_MODEL}")
        print(f"  {done} items cost ${rec.run_cost:.4f}  ->  ${per_item:.4f} per item")
        for reps in (1, 3):
            print(f"  projection for {full} items x {reps} repeat(s): ${per_item * full * reps:.2f}")
        print("  (projection includes the retries and thinking tokens these items actually used)")


if __name__ == "__main__":
    main()
