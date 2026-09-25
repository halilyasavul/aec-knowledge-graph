# eval/ — NL→IDS: text agreement vs execution outcome

v5 adds pipeline fixes (measured by ablation), graded metrics and symmetric test models.
Run directories: `v4-baseline-rescored` (v4 files, v5 metrics), `run2-fixed`,
`run3-no-trunc` (ablation), `run4-rep{1,2,3}` (determinism). `eval/RUNS_LABELS.json` maps
labels to directories; the v4 directory itself is frozen.

Step 1 (test set) lives in [nl_to_ids_testset/](nl_to_ids_testset/). This directory adds steps 2 and 3.

## Setup

    pip install lxml ifctester==0.8.5 ifcopenshell==0.8.5 pandas matplotlib rstr

    # sample models: the models are only a surface for detecting disagreement
    git clone --depth 1 --filter=blob:none --sparse https://github.com/buildingSMART/Sample-Test-Files eval/models_src/st
    git -C eval/models_src/st sparse-checkout set "IFC 4.3.2.0 (IFC 4.3 ADD2)/Simple-Scene"
    mkdir -p eval/models && cp eval/models_src/st/IFC*/Simple-Scene/*.ifc eval/models/

Generation needs the knowledge graph. To use a local rebuild instead of Aura, start
`neo4j:5` and run `python -m aec_kg.ingest_graph && python -m aec_kg.reingest_ucks` with
`NEO4J_URI/USER/PASSWORD` exported. Exported values take precedence over `.env`.
`run.json` records the graph's node counts, so a run records which graph it used.

## Run

    python -m eval.generate --run-id run2-fixed --ids-file eval/item_lists/v4_21.json
    python -m eval.generate --run-id run3-no-trunc --ids-file eval/item_lists/v4_21.json --no-truncation-fix
    python -m eval.score eval/runs/run2-fixed eval/nl_to_ids_testset/spec_tasks.jsonl eval/models
    python -m eval.score <frozen_run> <tasks> eval/models --out eval/runs/<new>   # score without touching it
    python -m eval.report eval/runs/v4-baseline-rescored eval/runs/run2-fixed     # side by side
    python -m eval.determinism eval/runs/run4-rep1 eval/runs/run4-rep2 eval/runs/run4-rep3
    python -m eval.determinacy      # drafts undetermined-facet annotations for human review

Default item pool: the IFC-only items (`--all` to include project-specific property sets).
Every v5 fix has an off switch: `--no-truncation-fix`, `--no-model-guards`, `--temperature`.

## Metrics

    S1  strict     identical verdict on every test object (the v4 headline)
    S2  graded     fraction of test objects both specifications judge the same way
    S3  decomposed requirement enforcement | false rejection | applicability (in/out of scope)

S2/S3 are reported for reference-derived objects, candidate-derived objects and pooled.
Only the reference-derived population is identical across runs, so cross-run comparisons use
`S2 on reference-derived objects`. Test models are synthetic and derived from the
specifications themselves: they measure agreement on each requirement's own boundary cases,
not on realistic building data.

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
- *Witness models* ([witness.py](witness.py)) are a third surface, `wit`, and the primary one.
  The sample buildings rarely contain the elements and properties a reference asks for, so a
  reference and a wrong candidate both fail everything and look equivalent. For each item,
  a small IFC4X3_ADD2 file is built **from the reference only**. It holds elements that satisfy
  it (`full`, every allowed enumeration value, inclusive bounds), elements that each break
  one requirement (`missing`, `badvalue`, `badtype`), and decoys just outside its applicability.
  `verify()` checks the reference behaves as labelled on its own witness: 181 of the 183
  buildable items verify, and so do all 20 in the first run. Controlled mutations
  (`harness.mutations`) go from 0/53 detected on the sample buildings to 176–177/177
  (dataType, pset, baseName, entity) and 140/151 (enumeration tightening).
  `wit_diverging` lists which variants the candidate judged differently.
- ifctester 0.8.5 quirk: a `predefinedType` restriction whose enumeration contains `USERDEFINED`
  compares equal to the string "USERDEFINED", so it only matches user-defined elements. It hits
  reference and candidate alike, and the witness is built for the checker as it behaves.

**report.py** prints outcome equivalence, the two conditional probabilities, F1 vs
equivalence (Spearman is withheld below 10 distinct F1 values), the error table, and cost and
latency. All items count; whether the request text names the property is shown only as a breakdown.
