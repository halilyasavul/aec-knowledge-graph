# Handover 2: held-out evaluation on Ishigaki-IDS-Bench, plus the three dev-set causes

You are a Claude Code agent on Halil's Windows machine, in this repository
(`C:\Users\halil\Documents\ifc-ai`, branch `eval-v7`). You have a shell; use it. The person does
not want to be asked to run anything or to decide anything this document already decides. Work
the job through to the report at the end, commit, push, stop.

Run 7 (the previous handover) is done: `eval/reports/v9/run7_summary.md`, commit `56f3817`.
Read it first; it tells you how the harness behaves on this machine (Neo4j container
`aeckg-eval-neo4j`, its password via `docker inspect`, the `NEO4J_*` variables every command
needs, the hidden CLI flags, the parent-environment leak the runner now strips). Then read
`eval/ishigaki_bench/README.md`, `eval/README.md`, `eval/reports/v9/README.md`.

## 0. Why this job

Every number so far is on the 47 development items: the system was tuned against them, their
references were trimmed by hand to what the requests say, and 47 items cannot resolve a claim
like "99%". Ishigaki-IDS-Bench (`eval/ishigaki_bench/data/test.jsonl`, CC BY 4.0) is 83 English
requests written by six BIM/IDS experts *before* the gold IDS, adjusted until the gold follows
uniquely from the request, and validated with the official audit tool. The system has never seen
them. A result on them is the first held-out number this project has.

Caveat to carry into the report: Ishigaki barely exercises the knowledge graph. Of ~290 property
facets in the English gold, 9 use a standard `Pset_`/`Qto_` set; 227 use the benchmark's
convention for "any user-defined property set", the regex `^(?!(Pset_|Qto_)).+`, with the
request's own words as property names ("Slip resistance coefficient"). It tests transcription,
IDS syntax and value constraints, not IFC vocabulary mapping.

## 1. Order of work

A. Three dev-set causes (small, ours). B. Ishigaki stage 1: the 41 harness-native items.
C. Ishigaki stage 2: the other 42 (harness extension). D. Opus rows. E. Report.
If time or the usage window runs out, stop after any completed stage, write the report for what
is done, and say what is not.

Held-out discipline: **never open a gold IDS from `test.jsonl` while editing the generator,
the prompt or the server instructions.** Stage A edits the generator; do it before touching
Ishigaki. The conversion script in stage B reads gold mechanically; that is fine. If you later
need a generator change because of what Ishigaki shows, make it, start a new run id, and report
both runs.

## A. The three remaining dev-set causes

From `run7_summary.md` §4. Each is one small change plus a test; rerun the 47 items once at
the end of A (`run8-claude-rep1`, `--model sonnet`) and score the seven variants as before.

1. **Graph gap — `ifc_type` missing.** `Pset_RailingCommon.Height` has no `ifc_type`, so the
   model omitted `dataType` and the reference's `IFCPOSITIVELENGTHMEASURE` went unmatched.
   Count the gap first: `MATCH (p:Property) WHERE p.ifc_type IS NULL RETURN count(p)` against
   the total, and list the 30 most-used property sets with gaps. Look at how `ifc_type` is
   derived in `aec_kg/ingest_graph.py` (parsed from bSDD description text) and extend the
   parser for the cases that are failing (bSDD gives the data type in the property's
   `dataType`/`physicalQuantity`/`units` fields too; `data/ifc-4.3.json` is the source — inspect
   `Height` under `Pset_RailingCommon` there). Re-ingest the typed field only (`ingest_graph`
   has a `reingest`-style path for `ifc_type`? if not, add a `--only-ifc-type` option that
   SETs the property on existing nodes rather than rebuilding). Record before/after counts.
   Regenerate the snapshots `graph_psets.json`/`graph_ptypes.json` in the new run directory
   only; do not overwrite those in old run directories.

2. **`partOf` not supported by the document model.** Vienna#25's model tried
   `partOf IFCBUILDINGSTOREY` and `generate_ids` rejected it (Pydantic). Add `PartOfFacet`
   (`entity`: IdsValue with name/predefinedType, `relation` optional, `cardinality`,
   `instructions`) and `ClassificationFacet` (`system`, `value`), and `MaterialFacet`
   (`value`), to `aec_kg/ids/models.py` `Requirements`, serialise them in
   `aec_kg/ids/serializer.py` per the IDS 1.0 XSD (`data/ids.xsd`), and mention them in the
   server instructions' document shape. Tests: each facet round-trips to XSD-valid XML.
   `eval/score.py` already handles these facet kinds in `canon()`/`loose_key()`.

3. **`oma_input#10` — reference marks `HandicapAccessible`/`FireExit` as `optional`.** The
   request says "Indication that / whether …"; our rule requires the property. Do not change
   the rule. Add a row to `eval/annotations/determinacy.jsonl` is *not* the right place either
   (that file is about values). Instead add `eval/annotations/cardinality.jsonl` with
   `{"id": "IDS_oma_input.ids#10", "facet_index": <i>, "scope": "cardinality", "reason": "request
   says 'indication whether'; required is the faithful reading; reference says optional"}` for
   the two facets, extend `relax()` in `eval/score.py` to treat `scope=cardinality` as "drop the
   cardinality from the comparison" (set it to the candidate's), and make the relaxed reference
   use it. Keep this minimal and documented in `eval/reports/v9/README.md`; it is the same kind
   of correction as `value_extend`.

Then: `python -X utf8 -m pytest -q` green; run8 on the 47 items; score; add
`"Run 8 (Sonnet 5.5, dev fixes, 47 items x 1)"` to `GROUPS` in `eval/analysis_probe.py`;
rerun `analysis_probe`, `analysis_extras`, `replay_checks run8-claude-rep1`.

## B. Ishigaki stage 1 — the 41 harness-native items

Harness-native = single specification, applicability holds only an entity facet, single turn.
That is 29 natural-language + 12 CSV rows (count them yourself from `test.jsonl`; the number
41 was computed on 22 Oct).

1. **Convert.** Write `eval/ishigaki_bench/convert.py` that reads `test.jsonl`, keeps
   `language == "en"`, and writes `eval/ishigaki_bench/spec_tasks_en.jsonl` in the same item
   shape as `eval/nl_to_ids_testset/spec_tasks.jsonl`: `id` (= `row-00NN`), `source`
   (`ishigaki`), `ids_title`, `spec_name`, `applicability` ({entity, predefinedType} from the
   gold's first spec), `n_requirements`, `prompt` ({"applies_to": {...}, "requirements": [...]})
   and `target` (facets flattened with the same `facet_target()` from
   `eval/nl_to_ids_testset/extract_testset.py`, so `canon()` matches). Also store
   `ifc_versions`, `input_format`, `turn_type`, `domain`, `n_specs`,
   `applicability_kinds`, and a flag `harness_native`. For the prompt: the user message
   *after* the `IDS Version: …` / `filename: …` header lines is the request; keep it verbatim
   as ONE requirement string (do not split it: the harness's `build_message` numbers the list,
   and Ishigaki's inputs are already structured). `applies_to` must come from the gold's
   applicability entity — that is how the dev set is built too (`extract_testset.py` puts the
   entity in the prompt). Note in the report that the entity is therefore given, as it is for
   the dev set.
   Validate every gold file against `data/ids.xsd` (`aec_kg.ids.validator`) and record the
   count that fails, if any.

2. **The property-set convention.** The gold uses `^(?!(Pset_|Qto_)).+` for an unspecified
   property set. The benchmark gives every model this convention in its task instruction; do
   the same, in `eval/claude_system_prompt_ishigaki.md` (copy of the dev prompt plus two
   sentences: "When the request does not name a property set and no standard Pset_/Qto_ set
   holds the property, put it in a user-defined set: give `propertySet` as
   `{"restriction": {"pattern": "^(?!(Pset_|Qto_)).+"}}` and use the request's wording as
   `baseName`. Use the IFC version the request states as `ifcVersion`."). The server's
   `generate_ids` accepts a restriction on `propertySet` already (IdsValue). Pass the file with
   `--system-prompt-file` — add that option to `eval/generate_claude.py` (default stays the
   dev prompt) and record its sha in `run.json`.
   The witness builder must also understand a regex property set on the reference side: check
   `eval/witness.py` `_emit`; where a reference facet's `propertySet` is `RESTRICTION(pattern=…)`,
   emit the objects' property set under a fixed literal that matches the pattern, e.g.
   `UserPset`, and treat a candidate pattern the same way. Add a test.

3. **IFC version.** Gold declares IFC2X3/IFC4/IFC4X3_ADD2 in various combinations; the
   witness file is IFC4X3_ADD2 and the `wit` surface executes with `should_filter_version=False`
   (`vf0`), so version does not matter for the behavioural score. Standard-model surfaces
   `vf0`/`vf1` are secondary. Say so in the report.

4. **Run.** `python -X utf8 -m eval.generate_claude --run-id run9-ishigaki-rep1 --tasks
   eval/ishigaki_bench/spec_tasks_en.jsonl --ids-file eval/ishigaki_bench/item_lists/native_41.json
   --model sonnet --system-prompt-file eval/claude_system_prompt_ishigaki.md` (write the id
   list in step 1). The runner's `assert_no_leak` compares the message against the prompt; it
   will hold. Then score strict and strict+probe only — there are no determinacy or extras
   annotations for Ishigaki, and the point of the set is that none are needed:
   `python -X utf8 -m eval.score eval/runs/run9-ishigaki-rep1 eval/ishigaki_bench/spec_tasks_en.jsonl eval/models`
   and the same with `--probe`.
   Note `eval.score`'s `ifc_only` column reads `graph_psets`; Ishigaki items are mostly not
   IFC-only by that definition (custom psets). `analysis_probe.read()` filters `ifc_only == 1`,
   so for Ishigaki compute S1 directly from `scores*.csv` (`wit_outcome_equiv` mean over rows
   where it is not null) and do not add it to `GROUPS`.

5. **FacetF1 their way.** `eval/analysis_ishigaki.py` computes the IDS-Bench FacetF1 on our
   dev runs; point it (or a copy) at run9 against the gold files so the report can show our
   S1 next to the metric the benchmark publishes (their best zero-shot: 65.6% FacetF1,
   GPT-5.5; Content pass 33.1%). Also run the official `IDSAuditTool` if it is installable
   here (`dotnet tool install -g ids-tool` — .NET is on this machine; if it fails, say so and
   use `aec_kg.ids.validator` XSD validity instead) on every generated file, and report
   the pass rate: that is their "Content" column.

## C. Ishigaki stage 2 — the other 42 items

Three gaps, in order of how many items each unlocks (counts from 22 Oct):
- multi-spec gold, entity-only applicability, single turn: 7 items. Allow an item to carry a
  list of specs: `target` becomes per-spec, `build_reference()` writes all specs, the witness
  emits objects per spec into one file, and `compare()` already pools element verdicts.
  Candidate files with several specs are already parsed (`parse_candidate` concatenates
  requirements; keep a per-spec view for the witness).
- attribute/property facets in applicability (single turn): 8 items. The witness must emit
  objects that satisfy the applicability (set the attribute/property value) and decoys that do
  not. `applicability` in the item becomes the full facet list.
- multi-turn: 20 items. The input is `messages[:-1]`, a conversation. Render earlier turns as
  "Previous request:"/"Previous answer:" blocks in the prompt, or skip multi-turn and say so.
  Skipping is acceptable; multi-turn is a different task (editing an existing IDS).

Do what fits; each unlocked group runs with the same command and run id suffix `-s2`.

## D. Opus rows

`--model opus` on the 47 dev items (`run8-opus-rep1`, with the stage-A fixes) and on the
Ishigaki items (`run9-ishigaki-opus-rep1`). Same scoring. One repeat each.

## E. Report — `eval/reports/v9/heldout_summary.md`

1. Stage A: what changed, the `ifc_type` gap before/after, run8 vs run7 on the 47 items under
   the four scorings × two object sets (S1 counts and intervals from `e2`), the three items.
2. Ishigaki stage 1: items run / ok / no_file; S1 strict standard and probe with a bootstrap
   interval over items (reuse `rate_ci` from `eval/analysis_probe.py`); facet F1 (ours) and
   FacetF1 (theirs) and audit-tool pass rate; the failing items with the first differing
   object and your one-line reading of why; a split by `input_format` (NL vs CSV).
3. Stage 2 if done, same shape.
4. Opus vs Sonnet, paired by item, on both sets.
5. The caveats: entity given in the prompt; property-set convention given; version ignored at
   execution; what Ishigaki does not test (the graph). Keep these honest and short.
6. Problems hit and what you changed.

Commit everything except `eval/runs/` with messages starting `v9:`, ending with

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GLv5SiHMFHiyxdS8P3M9UM
```

and push to `origin/eval-v7`.

## Rules

- Never read a gold IDS while changing the generator, prompt or server instructions.
- Do not edit `eval/nl_to_ids_testset/spec_tasks.jsonl` or existing run directories.
- Metric code (`score.py` `compare`/`graded`/`verdicts`, `witness.py` labels) stays as it is;
  additions for new facet kinds and regex property sets are fine and must be tested.
- No Gemini API calls. `python -X utf8 -m pytest -q` must stay green.
- Do not ask the person to run commands. If something cannot be done from your shell, write
  what and why into the report and stop.
