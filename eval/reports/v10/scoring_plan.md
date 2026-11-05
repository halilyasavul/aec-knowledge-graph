# v10b scoring plan — usBridge (fixed before any run, 2026-11-04)

Code: `eval/usbridge/score_usbridge.py` (additive; `eval/score.py` and `eval/witness.py` default paths unchanged).
Reference: the corrected usBridge IDS (`reference/corrections.json`). Items: `items.jsonl` (60 entity + 1 document).
Conditions: `--dictionaries ifc` and `--dictionaries ifc,usbridge`; same model, system prompt
(`eval/claude_system_prompt_usbridge.md`), message template and items. The flag is the only difference.

## Two granularities per item

| | (a) set-level | (b) property-level, determined subset |
|---|---|---|
| reference | the item's specs as HDR published them, unexpanded (`specs.jsonl`) | the item's specs expanded (`specs_expanded.jsonl`), kept to the facets an IDM-1 row states (`annotations/determinacy.jsonl`); value dropped where only the value is undetermined; specs left empty are dropped |
| size | 4,226 class-like facets in 208 specs | 476 facets over the entity items; 1,003 in the document item; 5 entity items have none (reported, not scored) |
| candidate | the generated IDS projected to set level: each property set it names becomes one set facet (`baseName` = any; required if any of its properties is required) | the generated IDS as written |
| unit | per spec: (entity, predefinedType) + facet key; property → (set, cardinality); attribute → (name, cardinality); partOf → (whole, its type, relation); classification → (present, cardinality); material → (present, cardinality); values and data types not compared | `eval.score` unchanged: canonical facet incl. value, dataType, cardinality |
| measure | facet precision / recall / F1, micro over items; spec match = share of reference (entity, predefinedType) the candidate has | **S1 behaviour match** on the witness model (verdict on every reference object equal); facet F1 beside it |
| cardinality | as published | the IDM says "all listed properties are required (when present)"; where HDR made a determined facet optional (193 entity-item facets) the candidate's cardinality is adopted (`scope=cardinality`, as for the dev set) |

## Reporting

| order | what |
|---|---|
| 1 (headline) | (b) S1, per condition, items with ≥ 1 determined facet; 95% bootstrap over items; paired ifc vs ifc,usbridge (better / worse / same) |
| 2 | (a) facet F1 and spec match, per condition |
| 3 | failure classes from (b) facets, counted per condition: entity mapping (reference spec's entity+type absent), property-set choice (property found under another set), property name (set right, name not in it), cardinality (same facet, other cardinality), missing facet, extra facet (in no reference spec of the item at all) |
| 4 | cost, tokens, tool calls per item |
| appendix | strict-all: (b) against the full expanded reference, no determinacy, no cardinality adoption |

## Gates before the pilot

| gate | must be |
|---|---|
| reference vs reference, (a) | facet F1 = 1.000 on all 61 items |
| reference vs reference, (b) | S1 = 1 and witness verified on every item with ≥ 1 determined facet |
| dry run, both conditions | stubbed answer scored end to end; flag visible in the server log and run.json |

## Fixed in advance

- No re-annotation after seeing outputs. Corrections to `determinacy.jsonl` or `alignment.csv` after the pilot get a new file and are reported with and without.
- No generator change between conditions; a generator change after the pilot means a new run id, both reported.
- Stop the pilot if any of the first 10 items costs more than $1.00.
