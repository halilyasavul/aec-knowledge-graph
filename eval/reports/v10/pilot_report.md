# v10b — usBridge: ceiling, graph-server flag, pilot (1 rep, 2 conditions)

Branch `eval-v7`. Claude Sonnet 5.5 via Claude Code (subscription), 2026-11-04. Scoring as fixed in `scoring_plan.md`. Totals in `eval/usbridge/summary/` (`kg_coverage.json`, `flag_proof.json`, `gate.json`, `pilot.json`).

## 1. KG coverage after step 2 (requirement targets of the corrected reference, 4,226 facets)

| target | n | IFC 4.3 only | + usBridge (bSDD + workbook definitions) |
|---|---|---|---|
| entity / attribute | 139 / 284 | 100% / 100% | 100% / 100% |
| predefinedType | 107 | 43.9% | 97.2% |
| property set / property | 3,548 / 3,403 | 31.0% / 32.1% | 100.0% / 100.0% |
| dataType | 3,402 | 30.4% | 96.9% |
| enumeration, exact / case-insensitive | 280 | 36.8% / 36.8% | 37.5% / 100% |
| **all checks of a facet** | 3,971 | **35.3%** | **92.8%** (target ≥ 90%) |

Corrections (`reference/corrections.json`): 15 facets (Piercap ×5, Expansion Joint ×9, HELICAL_ANCHOR ×1); expanded facets 4,222 → 4,226. Workbook rows loaded: 479 set/property definitions (455 with IFC type, 24 enumerations); no cardinality, no entity→spec structure. IFC part of the graph unchanged (checksum `0e864f52bfa6439d`).

## 2. Server flag proof — `search_classes("Pier")`, real server over stdio

| `--dictionaries` | rows | tagged |
|---|---|---|
| `ifc` (default) | 7 (IfcBeamPIERCAP, IfcBridgePartPIER, …) | none (output as before) |
| `ifc,usbridge` | 12 | 7 `ifc` + 5 `usBridge` (Pier, Pier Cap, Pier Column, Pier Stem, Pier Wall) |

Prompt: dev prompt + one sentence, same file in both conditions. Dry run (stubbed answer, both conditions): flag in `run.json` and server args, scored end to end.

## 3. Harness gate (reference vs reference)

| granularity | result |
|---|---|
| (a) set-level | facet F1 = 1.000 on 61 / 61 items; spec match 61 / 61 |
| (b) determined subset | S1 = 1 on 56 / 56 scored items (5 have no determined facet); witness verified on all; facet F1 = 1.000 |

## 4. Pilot — 60 entity items + whole-document item, 1 rep

| (b) determined subset — headline | `ifc` | `ifc,usbridge` |
|---|---|---|
| S1, entity items (95% CI) | 0 / 55 = 0.000 [0, 0] | 1 / 55 = 0.018 [0, 0.055] |
| S1, whole document | 0 | 0 |
| facet F1, entity mean (95% CI) | 0.017 [0.003, 0.034] | **0.237** [0.169, 0.313] |
| facet F1, micro | 0.004 | 0.144 |
| paired S1 (usbridge vs ifc) | — | better 1, worse 0, same 55 |

| (a) set-level | `ifc` | `ifc,usbridge` |
|---|---|---|
| facet F1, entity mean (95% CI) | 0.033 [0.020, 0.047] | 0.054 [0.031, 0.081] |
| facet F1, micro / whole document | 0.021 / 0.020 | 0.045 / 0.044 |
| spec match (entity + predefinedType) | 0.232 [0.143, 0.325] | 0.212 [0.129, 0.303] |
| paired facet F1 | — | better 13, worse 5, same 43 |

| failure class (b, facets unless noted) | `ifc` | `ifc,usbridge` |
|---|---|---|
| entity mapping: reference specs with no candidate spec of that entity + type | 260 specs | 253 specs (131 other entity, 122 same entity, other/no type) |
| … facets under those unmapped specs | 1,285 | 1,251 (85% of 1,479) |
| correct, within matched specs | 0 | 81 |
| missing facet / property name / pset choice | 179 / 0 / 15 | 132 / 11 / 4 |
| cardinality / value or dataType | 0 / 0 | 0 / 0 |
| extra facet (in no reference spec of the item) | 1,827 | 883 |

| dictionary use (60 entity items) | `ifc` | `ifc,usbridge` |
|---|---|---|
| outputs with a usBrPset set / with custom (IDM-wording) sets | 2 / 57 | 27 / 36 |
| property facets in custom sets | 1,336 | 898 |
| `query_pset("usBrPset_…")` calls (empty in `ifc`) | 266 | 242 |

| cost and tokens | `ifc` | `ifc,usbridge` |
|---|---|---|
| items ok / no file | 61 / 0 | 61 / 0 |
| cost: total / entity mean / document | $9.99 / $0.137 / $1.80 | $12.37 / $0.188 / $1.10 |
| first 10: max per item (stop at $1.00) | $0.17 | $0.26 |
| per entity item, median: input / output (thinking) tokens | 70k / 5.2k (1.9k) | 110k / 5.9k (2.9k) |
| tool calls / wall time, median | 13.5 / 39 s | 13 / 45 s |

Appendix, strict-all (full expanded reference): S1 0 / 57 in both; facet F1 micro 0.001 vs 0.028. Total spend incl. probe: $22.41.

## 5. Notes

| | |
|---|---|
| deviations | whole-document item: `--max-turns 40 --timeout 1800` and the message through stdin (53k chars > Windows command line), both conditions; `ifc` used all 40 turns. Failure classes: first pass pooled facets across specs (counted spec-coverage gaps as "value or dataType"); re-run per matched spec, metric unchanged |
| reading | the dictionary moves facet F1 (0.02 → 0.24) but not behaviour: 85% of determined facets sit in specs whose entity + predefined type the model did not produce (IDM rarely names the type: "Bridge" → Girder Bridge, Slab Bridge), and half the outputs keep IDM group names as custom sets (server rule "never invent or translate a name") |

## 6. Recommendation on the 3-rep run

| | |
|---|---|
| verdict | **not yet**: S1 is at the floor in both conditions (1 / 55 vs 0 / 55); three repeats cannot resolve a difference there. The facet-level effect is already clear at 1 rep (paired 13 vs 5 at set level; CIs of (b) facet F1 do not overlap) |
| before it | (1) annotate whether the IDM states each reference spec's predefined type (applicability determinacy, new file, pilot rescored with and without); (2) decide whether a usBridge-specific server rule — use the dictionary's set and property names for the IDM's property groups — is in scope (a generator change: new run id, both reported) |
| then | 60 + 1 items × 3 reps, `ifc,usbridge` only, `ifc` kept at this 1 rep as control: ≈ $37 (both conditions ≈ $67) |
