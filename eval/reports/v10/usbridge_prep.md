# v10 — US Bridge Design-to-Construction test set: preparation (no model calls)

Input: AASHTO IDM 1st Ed. (2023) Section 4. Reference: usBridge 2.0 IDS (IDM 2.0 App. 4, HDR, 2026). Built 2026-11-04. Scripts: `eval/usbridge/*.py`. Figures as of v10 (published reference); v10b corrections change them slightly (see `summary/`).

## 1. Reference specs parsed (`reference/specs.jsonl`, `specs_expanded.jsonl`; counts in `summary/counts.json`)

| file | specs | requirement facets | whole-set facets | expanded: sets → properties | expanded facets |
|---|---|---|---|---|---|
| General | 17 | 22 | 3 | 3 | 39 |
| SpatialBreakdown | 45 | 285 | 114 | 114 | 705 |
| Classes | 146 | 1,206 | 717 | 571 (+144 prohibited kept, 2 no spec) | 3,478 |
| PropertySets | 130 | 646 | — | (source of expansion) | — |
| **total (class-like)** | **208** | 1,513 | 834 | 688 | **4,222** |

Expansion cardinality: set required + property required → required; otherwise optional; prohibited sets stay set-level.

| reference defect (as published, not fixed) | effect |
|---|---|
| `usBrPset_Piercap` ×5 (set is `usBrPset_PierCap`) | Pier Cap never gets its set; 4 prohibitions void |
| `usBrPset` (truncated) on Counterfort | unexpandable |
| `usBrPset_Expansion Joint` (space) vs `usBrPset_ExpansionJoint` | 7 properties not in bSDD |
| `HELICAL_ANHCOR` in IfcElementAssembly whitelist | typo predefined type |
| `usBrPset_PierCap`, `usBrPset_PrecastUnit` defined, used by no spec | — |
| 7 applicability groups shared by 2 specs | both apply to the same objects |

## 2. Workbook and bSDD (`reference/workbook_entities.jsonl`, `concepts.jsonl`; counts in `summary/workbook_vs_bsdd.json`)

| workbook | n | bSDD `usTransportation/usBridge/1` (Preview) | n |
|---|---|---|---|
| entity tabs / entity rows | 54 / 191 | classes (Class) / property-set records / properties | 175 / 89 / 399 |
| rows with DD name | 179 | cached responses (`bsdd/`) | 995 |
| usBridge psets / IFC psets | 89 / 41 | | |
| concepts / mapped to IFC | 402 / 261 | | |

| workbook vs bSDD difference | count |
|---|---|
| DD name not a bSDD class (Site→`usBridge_Site`, CIP wall→`RetainingWallCIP`, 3 "Not Included" layers, Reinforced Soil Footing) | 6 |
| bSDD class not in workbook (`usBridge_Key`, `_RetainingWallCIP`, `_Site`) | 3 |
| Industry Name ≠ bSDD name ("Culvert" vs "Culvert (Facility)", …) | 18 |
| set/property on workbook entity, not on bSDD class (distinct) | 94 |
| set/property on bSDD class, not on workbook entity (distinct; 140 rows are `usBrPset_SubstructureCommon`) | 74 |
| data type: IfcDate/IfcDuration vs bSDD "Time" | 7 |
| enumeration differs (6 × workbook "See SNBI" vs bSDD list; TendonType spelling; BarPosition) | 8 |
| IFC class differs (Keyway: workbook IfcProjectionElement, bSDD IfcVirtualElement) | 1 |

## 3. IDM-1 Section 4 parsed (`idm/entities.jsonl`, `idm/section4.json`)

| subsections | entities | property groups | properties | watermark lines removed | labels inferred |
|---|---|---|---|---|---|
| 13 (4.1.1–4.1.13) | 69 | 333 | 1,466 | 416 | 1 (p. 4-11 rows → Girder; next page "Girder (Continued)") |

Cardinality rule (IDM 4.1): "All listed properties are required (when present) to satisfy the exchange."

## 4. Alignment (`alignment.csv`, `summary/alignment_summary.json`)

| IDM-1 entities | exact | normalised | manual (reason per row) | unmatched | rows |
|---|---|---|---|---|---|
| 69 | 15 | 16 | 29 | 9 | 167 |

| unmatched IDM-1 (no usBridge class/spec) | reference side not reached |
|---|---|
| Cross Section, Architectural Feature, Seal Coat/Tremie Seal, Bent Plate, Field Splice, Weld, Accessories, Environmental, Miscellaneous | workbook: 71 of 191 entities; IDS: 91 of 208 specs (36 "Predefined Types" whitelists, 55 classes HDR added: Site, culvert parts, anchors, couplers, rivets, …) |

## 5. Items (`items.jsonl`)

| setting | items | request (chars, median / max) | IDM properties | reference specs per item |
|---|---|---|---|---|
| entity | 60 | 1,044 / 3,374 | median 18.5, total 1,374 | median 2 (1–8) |
| whole Section 4 | 1 | 52,961 | 1,466 | 208 (117 reached by alignment) |

No IFC/Pset/usBr names in any request. Entity given only in IDM wording.

## 6. Determinacy (`annotations/determinacy.jsonl`) — machine-made, not human-reviewed

| | facets | determined | undetermined | determined but ref. optional | value undetermined |
|---|---|---|---|---|---|
| entity items (Σ over items) | 4,533 | 476 (10.5%) | 4,057 | 193 | 2 |
| document item | 4,222 | 1,003 (23.8%) | 3,219 | 297 | 2 |

| kind (entity items) | property | attribute | material | partOf | classification | entity |
|---|---|---|---|---|---|---|
| determined / facets | 263 / 3,931 | 112 / 270 | 92 / 99 | 9 / 95 | 0 / 136 | 0 / 2 |

| method | lexical exact | lexical cover | reading | attribute rule | material rule | section (partOf) |
|---|---|---|---|---|---|---|
| entity items | 64 | 130 | 69 | 112 | 92 | 9 |

Quality: 71 distinct lexical-cover matches read, 2 doubtful (≈97%); 418 distinct near-misses read, 50 accepted as readings; recall below the near-miss threshold not measured. Per-item determined share: median 11%, max 26%, 5 items 0%.

## 7. KG coverage (`summary/kg_coverage.json`, `summary/kg_load.json`) — usBridge loaded as `UsBridgeClass/PropertySet/Property`; IFC part unchanged (counts, 45,116 rels, checksum `0e864f52bfa6439d`)

| requirement target | n | IFC 4.3 only | + usBridge |
|---|---|---|---|
| entity | 139 | 100% | 100% |
| predefinedType | 107 | 44% | 97% |
| attribute | 284 | 100% | 100% |
| property set | 3,544 | 31% | 100% (3,530) |
| property | 3,398 | 32% | 100% (3,389) |
| dataType | 3,397 | 30% | 51% |
| enumeration (exact / case-insensitive) | 280 | 37% / 37% | 38% / 100% |
| **all checks of the facet** | 3,967 | **35%** | **54%** |
| applicability (entity + type) | 208 | 64% | 98% |

usBridge data types: bSDD gives "String"/"Real" only (142 → IFCLABEL by the existing rule, 257 none). 149 classification + 106 material facets are not graph targets.

## 8. Harness (`summary/harness_check.json`) — scorer unchanged

| run (61 items) | facet F1 = 1 | XSD valid | S1 = 1 (witness) | sample models equal | witness unverified |
|---|---|---|---|---|---|
| expanded reference vs itself | 61 | 61 | 37 / 37 | 23 / 23 | 23 |
| official HDR XML vs flattened reference | 61 | 61 | 37 / 37 | 23 / 23 | 23 |

| witness gap (builder, before v10b) | effect |
|---|---|
| single required enumeration value (`CompositionType = ELEMENT`) set to the enum's first member | objects built to pass fail |
| properties on type objects (`IfcReinforcingBarType`) attached by relation, not `HasPropertySets` | set not found |
| user-defined type of a type object in `ObjectType`, not `ElementType`; `IfcBuiltElement` (no PredefinedType) | object not in scope |
| partOf whole given as pattern `.*` | whole not built |
| overlapping specs (class-wide spec + typed spec; all types claimed) | decoys in scope; objects miss the wider spec |

Closed in v10b behind `witness.EXTENSIONS` (off by default); gate in `summary/gate.json`.

## 9. Proposed run (not started)

| | |
|---|---|
| items | 60 entity × 3 reps; whole-document × 1 (after a 5-item pilot) |
| model | Claude Sonnet 5.5 via Claude Code (Run 7–9 runner); Opus × 1 rep afterwards |
| prerequisite | MCP server reads `UsBridge*` labels (today IFC only → ceiling 35%, with them 54%); runner `--tasks` for `items.jsonl` (`request_text` only) |
| scoring | determined-only first, strict second; S1 on witness |
| measured basis | Sonnet $0.040/item (dev, 0.7k out), $0.099/item (Ishigaki, 1.9k out); Opus ×1.9 |
| estimate (API prices; runs use the subscription) | entity: $0.10–0.25/item → **$18–45** for 180 item-runs; document: $3–10/rep; Opus 1 rep ≈ $11–28 |
| rights | IDM-1 (AASHTO, "no reproduction"), IDS/workbook (HDR), bSDD ("rights reserved"): derived data not committed (v10b repo split; `python -m eval.usbridge.build` rebuilds it) |
