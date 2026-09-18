# eval/ — NL→IDS: facet F1 vs execution outcome

Step 1 (test set) lives in [nl_to_ids_testset/](nl_to_ids_testset/). This directory adds steps 2 and 3.

## Setup

    pip install lxml ifctester==0.8.5 ifcopenshell==0.8.5 pandas matplotlib

    # sample models: the models are only a surface for detecting disagreement
    git clone --depth 1 --filter=blob:none --sparse https://github.com/buildingSMART/Sample-Test-Files eval/models_src/st
    git -C eval/models_src/st sparse-checkout set "IFC 4.3.2.0 (IFC 4.3 ADD2)/Simple-Scene"
    mkdir -p eval/models && cp eval/models_src/st/IFC*/Simple-Scene/*.ifc eval/models/

Generation needs the knowledge graph. To use a local rebuild instead of Aura, start
`neo4j:5` and run `python -m aec_kg.ingest_graph && python -m aec_kg.reingest_ucks` with
`NEO4J_URI/USER/PASSWORD` exported. Exported values take precedence over `.env`.
`run.json` records the graph's node counts, so a run records which graph it used.

## Run

    python -m eval.generate --limit 20            # resumable; writes eval/runs/<run_id>/
    python -m eval.score eval/runs/spec_gemini-2.5-flash eval/nl_to_ids_testset/spec_tasks.jsonl eval/models
    python -m eval.report eval/runs/spec_gemini-2.5-flash

`eval/runs/` is git-ignored because `log.jsonl` holds raw graph tool results (bSDD-derived).

## What each step does

**generate.py** calls the shipped `aec_kg.main_orchestrator.run_agent` unchanged. It
instruments `_call_with_retry` (tokens, model version, latency) and `dispatch_tool` (every
tool call and its full result). Only `item["prompt"]` is rendered into the user turn, and
`assert_no_leak` checks this on every item. The model is `gemini-2.5-flash`, asserted to be
API version `001` at start-up and on every response. The run aborts if the version changes.
Temperature is unset, as it is in the app (the API default is recorded in `run.json`). The
IDS XSD runs in strict mode (`aec_kg.ids.validator`, `IDS_XSD_STRICT`), so a missing
validator raises instead of passing.

**score.py** writes `scores.csv` (per item) and `pairs.csv` (per item × model × mode).
- *Intensional:* multiset facet P/R/F1 of the requirement facets against `target`, using the same
  `facet_target()` flattening that built the targets. Entity names, predefined types and
  dataTypes are uppercased, restriction members are sorted, `uri` is ignored, and a missing
  cardinality counts as `required`. A name-level "loose" F1 is also recorded.
- *Extensional:* a reference IDS is rebuilt from `applicability` + `target` (all 185 are
  XSD-valid and round-trip to their targets exactly). Both reference and candidate run on every
  model, and the element GUID sets are pooled across models. (item, model) pairs where the
  reference applies to 0 elements are skipped and counted. Each item is scored in two modes:
  `vf0` ignores `ifcVersion` at execution, and `vf1` uses `should_filter_version=True`.
- The executor is cross-checked against `harness.run()` on the first 25 pairs.

**report.py** prints outcome equivalence, the two conditional probabilities, F1 vs
equivalence (Spearman is withheld below 10 distinct F1 values), the error table, and cost and
latency. Headline numbers use non-leaked items only.
