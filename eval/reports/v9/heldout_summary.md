# Held-out evaluation on Ishigaki-IDS-Bench, and the three dev-set causes

Handover 2, run 21–22 Oct 2026 on the subscription login (Claude Code 2.1.296, the `ifc` MCP
server only, as in Run 7). There are five parts:

- **Stage A** fixes the three causes `run7_summary.md` §4 found, and reruns the 47 dev items as
  Run 8.
- **Stage B** runs the 41 harness-native Ishigaki items: the first held-out number this project
  has.
- **Stage C** extends the scorer to 20 more single-turn items.
- **Stage D** adds Opus rows.
- **Run 10** fixes the one generator gap stage C exposed, and reruns. For stage 2 it is not
  held-out clean; see §3.

Short version: on the dev set the three fixes net to zero for Sonnet (§1). On the held-out set,
Sonnet is behaviour-exact on 12 of 38 verifiable stage-1 items (0.316, interval 0.18–0.47).
Its FacetF1 the benchmark's way is 0.650 without the IFC-version block (0.590 with it). The paper's
best zero-shot is 65.6%, as the handover cites it. Most failures are the system doing what it was
built to do — mapping request words onto standard IFC properties — where the benchmark's gold keeps
the request's own words in a user-defined set. The request checks, tuned on the dev set, fire on
held-out requests and sometimes push the model away from the gold. Opus is no better than Sonnet
on the dev set and worse on the held-out set. buildingSMART's official audit passes every generated
file's structure and fails every one on content (0 of 183; all 61 gold files pass). That is mostly
two serializer defaults, not the model: without them, about nine in ten of Sonnet's files would pass.

## 1. Stage A: the three dev-set causes

| cause (Run 7) | change | test |
| --- | --- | --- |
| `Pset_RailingCommon.Height` has no `ifc_type`, so no `dataType` was written | **Per-set types from the property set templates.** ifcopenshell ships buildingSMART's IfcPropertySetTemplate library. `python -m aec_kg.ingest_graph --only-ifc-type` writes each untyped pair's type onto the `HAS_PROPERTY` relationship. The type is per set because one code can differ: `Height` is IfcPositiveLengthMeasure in `Pset_RailingCommon` and a length quantity in `Qto_*`. Readers take `coalesce(rel, node)`. Only defined types qualify; template entities such as IfcTimeSeries do not. A full rebuild runs the same step. | `test_template_types_*` |
| Vienna#25: `partOf IFCBUILDINGSTOREY` rejected by the document model | **`PartOfFacet`, `ClassificationFacet` and `MaterialFacet` in `Requirements`.** The serializer writes them in XSD order; partOf takes cardinality required/prohibited only. The server instructions name them on a separate line, "only when the request asks for them". | `test_new_facets_*`, `test_bad_part_of_*` |
| oma_input#10: the reference marks `HandicapAccessible` / `FireExit` optional | **`eval/annotations/cardinality.jsonl`.** For these two facets, relaxed scoring takes the candidate's cardinality instead of the reference's (`relax` + `adopt_cardinality`). Documented in `README.md` §C. | `test_cardinality_annotation_*` |

The data-type gap, counted on set/property pairs: 635 of 3,683 untyped before (383 of the 2,396
linked properties), 273 after. All 273 left are reference-valued properties whose template type is
an entity: IfcTimeSeries 223, IfcExternalReference 27, IfcMaterialDefinition 14,
IfcDocumentReference 6, three others. None of these can be an IDS dataType. On the 2,219 pairs
already typed from the bSDD text, the templates agree on 97% (62 differ, e.g. NonNegative vs
Positive length). 91 of the "String → IFCLABEL" defaults differ from the template too. Both are
left as they were: only the gap was filled. The new runs' `graph_ptypes.json` differs from Run 7's
in exactly the 362 filled pairs.

Two generator changes were made before Ishigaki was opened. They make the generator consistent
with the Ishigaki prompt, which says "use the request's wording as `baseName`":

- the whitespace check now applies only to standard `Pset_`/`Qto_` sets;
- the prose and placeholder guards no longer apply to property-set and property names. The guard
  also rejected the standard name `Pset_SensorPHistory.Value`.

Neither fired in Run 7.

**Run 8 against Run 7 on the 47 dev items.** S1 exact over verifiable item-runs, with the 95% item
bootstrap from `e2_headline_three_scorings.csv`. Run 7 was rescored under the same scorer into
`run7-claude-rep*-rescored-v9b/`; its run directories are untouched. The cardinality annotation alone
moves Run 7 by +3/132.

| scoring | objects | Run 7 as committed (×3) | Run 7 rescored (×3) | Run 8 Sonnet (×1) | Run 8 Opus (×1) |
| --- | --- | --- | --- | --- | --- |
| strict | standard | 36/132 = 0.273 [0.14, 0.41] | 36/132 = 0.273 [0.16, 0.41] | 13/44 = 0.295 [0.16, 0.43] | 13/44 = 0.295 [0.16, 0.43] |
| strict | probe | 24/132 = 0.182 [0.07, 0.30] | 24/132 = 0.182 [0.07, 0.30] | 8/44 = 0.182 [0.07, 0.30] | 8/44 = 0.182 [0.09, 0.30] |
| determined-only | standard | 123/132 = 0.932 [0.84, 1.00] | 126/132 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] |
| determined-only | probe | 111/132 = 0.841 [0.73, 0.93] | 114/132 = 0.864 [0.75, 0.95] | 37/44 = 0.841 [0.73, 0.93] | 37/44 = 0.841 [0.73, 0.93] |
| determined-only + excused | standard | 123/132 = 0.932 [0.84, 1.00] | 126/132 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] |
| determined-only + excused | probe | 111/132 = 0.841 [0.73, 0.93] | 114/132 = 0.864 [0.75, 0.95] | 37/44 = 0.841 [0.73, 0.93] | 37/44 = 0.841 [0.73, 0.93] |
| request-determined + excused | standard | 123/132 = 0.932 [0.84, 1.00] | 126/132 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] |
| request-determined + excused | probe | 123/132 = 0.932 [0.84, 1.00] | 126/132 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] | 42/44 = 0.955 [0.89, 1.00] |

Facet F1 under request-determined: 0.905 (Run 7), 0.913 (Run 7 rescored), 0.918 (Run 8 Sonnet),
0.912 (Run 8 Opus), 0.920 (Run 10).

What happened to the three items:

- **Vienna#9: fixed.** `Height` now carries `IFCPOSITIVELENGTHMEASURE`, so the item is exact under
  strict and request-determined scoring. Under determined-only it still differs, by the German
  Status values only.
- **oma_input#10: exact under the relaxed scorings**, through the annotation. The output did not
  change.
- **Vienna#25: still fails, but for a different reason.** Both models now write
  `partOf IFCBUILDINGSTOREY` via IFCRELAGGREGATES on the first attempt; no validation errors are
  left in Run 8. The determined-only reference requires PredefinedType from a seven-value
  enumeration, and both models also add an `ÖNORM B 1800` classification. Now that the witness can
  build partOf, the failure reads correctly as over- and under-strict.

The cost: the new facets invite use. Sonnet turned IDS4ALL#2's descriptive "according to ÖNORM
A 6241-2 Annex A, a slab is a primary building element" into a required classification. Opus,
independently, required `PredefinedType` there. In Run 7, Sonnet had left that request without
requirements in all three repeats. Net on the dev set: +1 (Vienna#9), −1 (IDS4ALL#2). This was
not tuned away: it is one dev item, and the Ishigaki runs depended on the same instructions.

Run 8 logs, with the fixed token accounting:

| run | Sonnet | Opus |
| --- | --- | --- |
| wall time | 11.9 min | 15.7 min |
| median input tokens per item | 30.7k | 24.5k |
| output tokens (thinking) | 46.8k (6.3k) | 48.6k (7.0k) |
| reported cost (an estimate) | $1.87 | $3.54 |
| `generate_ids` | one call per item, none rejected | one call per item, none rejected |

The request checks fired on none of Run 8's 94 accepted documents.

**Opus against Sonnet on the dev set:** the same verdict on every item in every scoring. The only
difference is facet F1 on ArcDox#1, which is unverifiable.

## 2. Stage B: Ishigaki stage 1, the 41 harness-native items

**Conversion.** `eval/ishigaki_bench/convert.py` turns the 83 English rows into
`spec_tasks_en.jsonl`, in the dev-set item shape, with the targets flattened by the same
`facet_target()`. Harness-native means a single turn, one specification, and entity-only
applicability: 41 items, 29 natural-language and 12 CSV. All 83 gold files are XSD-valid. On the
witness models the rebuilt reference behaves exactly like the gold IDS on 38 of 41. The other 3 are
the unverifiable items below.

Each request is the user message after its `IDS Version:` / `filename:` lines, as one requirement
string. `applies_to` is the gold's entity. Generation used
`eval/claude_system_prompt_ishigaki.md`: the dev prompt plus the property-set-convention sentences
(sha `25c5922c…`, in `run.json`).

**Result.**

| | Sonnet 5.5 (Run 9) | Opus 5.5 (Run 9) | Sonnet, Run 10 |
| --- | --- | --- | --- |
| items run / ok / no_file | 41 / 41 / 0 | 41 / 41 / 0 | 41 / 41 / 0 |
| S1 strict, standard objects | 12/38 = 0.316 [0.18, 0.47] | 7/38 = 0.184 [0.08, 0.32] | 12/38 = 0.316 [0.16, 0.47] |
| S1 strict, probe objects | 12/38 = 0.316 [0.18, 0.47] | 7/38 = 0.184 [0.08, 0.32] | 12/38 = 0.316 [0.16, 0.47] |
| facet F1, ours (requirements only) | 0.553 | 0.304 | 0.555 |
| FacetF1 their way, with version block | 0.590 | 0.454 | 0.591 |
| FacetF1 their way, version block excluded | 0.650 | 0.478 | 0.651 |
| official audit, full (the paper's "Content") | **0/41** | **0/41** | **0/41** |
| official audit, structure only (`-c`) | 41/41 | 41/41 | 41/41 |
| full audit if the serializer wrote applicability occurs and numeric restriction bases | 37/41 | 31/41 | 38/41 |

"Their way" follows `eval/analysis_ishigaki.py`: blocks keyed by side, facet type and content,
the version as one more block, classification/material/partOf excluded, macro over items, scored
against the gold IDS itself.

The paper's best zero-shot is 65.6% FacetF1 (GPT-5.5) and 33.1% "Content" pass, as the handover
cites them. Those were computed on the whole benchmark and with the version given, and our FacetF1
is our reading of theirs. So "about at the paper's best" is as far as that comparison goes.

**The official audit** (`eval/ishigaki_bench/audit.py`, `h7_ishigaki_audit*.csv`) uses
buildingSMART's IDS-Audit-tool, `ids-tool` 1.0.124, installed with your approval as the NuGet
package `ids-tool.commandline`. Every file was audited twice: the full audit (structure plus the
"agreed limitation of IDS contents") and the structure audit alone (`-c`).

- **All 61 gold files pass the full audit**, which confirms the tool and the conversion agree.
- **Every generated file passes the structure audit and fails the full audit**, for both models
  and both runs.

The failures are mostly two defaults in our serializer, not the model:

| code | message | cause | files (Sonnet stage 1) |
| --- | --- | --- | --- |
| 301 | invalid cardinality on `applicability`: [1..1] breaks the implementation agreements | the serializer writes no `minOccurs`/`maxOccurs` unless the model asks; the IDS default is exactly one element. The gold writes 0..unbounded. | 41 of 41 |
| 303, 308 | numeric bounds on an `xs:string` restriction base / `xs:string` base for a measure type | `IdsRestriction.base` defaults to `xs:string` and the instructions never mention it | 15 and 14 |
| 203 | a `value` without a `dataType` | the model; Opus drops dataTypes (9 Opus files) | 1 |
| 103 | invalid attribute name ("Temporary height") | the model (rows 0080/0082, see below) | 2 |
| 305 | `TRUE` for `xs:boolean`, `1/20` for `xs:double` | the model | 0 |
| 202 | a `prohibited` property with a `dataType` | the model | 1 |

Counting the files whose only full-audit errors are 301, 303 and 308 gives what the two serializer
defaults cost. With them fixed, Sonnet would pass 37 of 41 stage-1 files (Opus 31, Run 10 38): far
above the paper's 33.1%, where we now stand at 0. The S1 numbers are unaffected: ifctester tolerates
both defaults, and the behavioural score reads per-element verdicts, not the specification's
cardinality.

By input format (Sonnet, Run 9):

| format | items | S1 (probe) | FacetF1 | FacetF1, no version |
| --- | --- | --- | --- | --- |
| natural language | 29 | 0.296 | 0.596 | 0.634 |
| CSV | 12 | 0.364 | 0.576 | 0.691 |

**Why the item-runs fail.** `h5_ishigaki_failure_causes.csv` compares each gold requirement with
the candidate by identity. Sonnet (Run 9) had 26 failing item-runs:

- **Mapped to IFC vocabulary: 13**, 7 of them with no other difference. "Building area" →
  `Qto_BuildingBaseQuantities.FootPrintArea`, "Use" → `Pset_BuildingCommon.OccupancyType`,
  "Span" → `Pset_BeamCommon.Span`, "Thermal transmittance" →
  `Pset_DoorWindowGlazingType.ThermalTransmittanceWinter`. The gold keeps the request's words in a
  user-defined set. The prompt does say a user-defined set is for when *no* standard set holds the
  property; the model judged that one did. In rows 0140/0144 the request uses the standard name
  `NominalAirFlowRate` itself, and the gold still puts it in a user-defined set.
- **DataType chosen differently: 10.** On user-defined properties, where the graph has no type,
  Sonnet often writes IFCLABEL where the gold has IFCIDENTIFIER, IFCBOOLEAN, IFCDATE or
  IFCDURATION: 7, 5, 4 and 2 facets across stages 1 and 2. It also writes
  IFCPOSITIVERATIOMEASURE where the gold has IFCRATIOMEASURE.
- **Requirement missing or added: 8 each.** Several are one gold specification split into three.
  In rows 0080/0082 the request's "Requirements Attribute(Name)" column lists values of the `Name`
  attribute ("Temporary height" present, the others prohibited). Sonnet wrote them as attributes
  named "Temporary height" and so on.
- **Value: 3.** "Yes" vs `true`; a bound dropped after a request check (below).
- **Applicability: 4.**

The `wit_direction` counts are dominated by `over_strict+under_strict` (18). A different property
set name makes the candidate reject the reference's objects and accept its own.

Three items are unverifiable under ifctester 0.8.5, the same 3 for every run:

- **row-0040:** ifctester compares bounds with `float()`, so a date bound such as `2029-03-31`
  fails for every value.
- **row-0098:** the gold puts two contradictory requirements on one property ("Finish material
  type" ∈ {Tile, Flooring, Carpet} and = "KNM-50", both in the user-defined set).
- **row-0166:** the gold pins an IFCBOOLEAN with `pattern=true`, and ifctester stringifies true as
  "True".

Every failing or unverifiable stage-1 item-run, Sonnet, Run 9. The differences column comes from
`h5`; the reading is the dominant cause:

| item | format | verdict | direction | first differing object | differences (gold vs candidate) | reading |
| --- | --- | --- | --- | --- | --- | --- |
| row-0010 | NL | failing | over_strict+under_strict | `cand:full:IFCBUILDING` | dataType user-set.Building coverage ratio: IFCRATIOMEASURE vs IFCPOSITIVERATIOMEASURE ; dataType user-set.Floor area ratio: IFCRATIOMEASURE vs IFCPOSITIVERATIOMEASURE ; mapped 'Building area' -> Qto_BuildingBaseQuantities.FootP... | mapped to IFC vocabulary where the gold keeps a user-defined property; dataType chosen differently |
| row-0040 | NL | unverified | witness_unverified | `` | value user-set.Warranty expiration date: RESTRICTION(minInclusive=2029-03-31) vs RESTRICTION(pattern=^(2029-03-31;2029-0[4-9]-(0[1-9];[12][0-9];3[01]);2029-1[0-2]-(0[1-9];[12][0-9];3[01]);(203[0-9];20[4-9][0-9];2[1-9][0-9]{2};[... | unverifiable under ifctester 0.8.5 (see caveats) |
| row-0046 | NL | failing | under_applicable+under_strict | `cand:full:IFCTRANSPORTELEMENT` | applicability: 1 gold spec(s) vs 1; gold facets ['entity'], candidate ['entity'] ; value user-set.Maintenance contract exists: true vs Yes ; dataType user-set.Maintenance contract exists: IFCBOOLEAN vs IFCLABEL | dataType chosen differently; value differs; applicability / spec split differs |
| row-0058 | NL | failing | over_strict+under_strict | `cand:full:IFCBUILDING` | dataType user-set.Project ID: IFCIDENTIFIER vs None ; mapped 'Building Name' -> Pset_Address.AddressLines ; missing user-set.Construction Site Address ; extra attribute Name | mapped to IFC vocabulary where the gold keeps a user-defined property; dataType chosen differently |
| row-0062 | NL | failing | over_strict+under_strict | `cand:full:IFCBUILDING` | mapped 'Use' -> Pset_BuildingCommon.OccupancyType ; mapped 'Fire resistance' -> Pset_BuildingCommon.FireProtectionClass | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0080 | NL | failing | under_strict | `ref:present:0` | applicability: 1 gold spec(s) vs 3; gold facets ['entity'], candidate ['entity'] ; missing attribute Name ; missing attribute Name ; missing attribute Name ; extra attribute Temporary height ; extra attribute Temporary slope ; ... | applicability / spec split differs; requirement missing; requirement added |
| row-0082 | CSV | failing | over_strict | `ref:full:IFCSLAB` | missing attribute Name ; missing attribute Name ; missing attribute Name ; extra attribute Temporary height ; extra attribute Temporary gradient ; extra attribute Temporary centerline number | requirement missing; requirement added |
| row-0088 | NL | failing | under_strict | `ref:present:2` | dataType user-set.Land rights holder name: None vs IFCLABEL ; dataType user-set.Land rights holder phone number: None vs IFCLABEL ; dataType user-set.Individual negotiation memo: None vs IFCTEXT | dataType chosen differently |
| row-0092 | NL | failing | over_strict+under_strict | `cand:full:IFCSPACE` | dataType user-set.Use Code_Developer A: IFCIDENTIFIER vs IFCLABEL | dataType chosen differently |
| row-0094 | NL | failing | under_strict | `cand:full:IFCBRIDGE` | dataType user-set.StructureName_InternalStandard: IFCTEXT vs None ; dataType user-set.FacilityName_Client: IFCTEXT vs None ; dataType user-set.FacilityID_Client: IFCIDENTIFIER vs None | dataType chosen differently |
| row-0096 | NL | failing | over_strict+under_strict | `cand:edge:0:maxInclusive` | mapped 'Thermal transmittance' -> Pset_DoorWindowGlazingType.ThermalTransmittanceWinter ; mapped 'Sound insulation rating' -> Pset_WindowCommon.AcousticRating ; mapped 'Product model number' -> Pset_ManufacturerTypeInformation.... | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0098 | NL | unverified | witness_unverified | `` | applicability: 1 gold spec(s) vs 1; gold facets ['entity'], candidate ['entity'] ; missing user-set.Finish material type | unverifiable under ifctester 0.8.5 (see caveats) |
| row-0100 | NL | failing | over_strict+under_strict | `cand:full:IFCSLAB` | mapped 'Product part number' -> Pset_ManufacturerTypeInformation.ArticleNumber | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0102 | NL | failing | over_strict+under_strict | `cand:full:IFCWALL` | dataType user-set.Finishing material product number: IFCIDENTIFIER vs IFCLABEL | dataType chosen differently |
| row-0106 | NL | failing | under_applicable+under_strict | `cand:badvalue:0` | applicability: 1 gold spec(s) vs 3; gold facets ['entity'], candidate ['entity'] ; missing Effective corridor width.Main corridor ; missing Effective corridor width.Secondary corridor ; missing Slip resistance coefficient of fl... | applicability / spec split differs; requirement missing; requirement added |
| row-0108 | NL | failing | under_applicable | `ref:altvalue:0:1` | applicability: 1 gold spec(s) vs 1; gold facets ['entity'], candidate ['entity'] | applicability / spec split differs |
| row-0112 | NL | failing | over_strict+under_strict | `cand:full:IFCBEAM` | missing user-set.Deflection limit ; extra user-set.Deflection | requirement missing; requirement added |
| row-0118 | NL | failing | over_strict+under_strict | `cand:full:IFCBEAM` | mapped 'span length' -> Pset_BeamCommon.Span | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0134 | CSV | failing | over_strict+under_strict | `cand:edge:0:maxInclusive` | mapped 'Span' -> Pset_BeamCommon.Span | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0136 | CSV | failing | over_strict+under_strict | `cand:edge:0:maxInclusive` | value user-set.Beam depth: RESTRICTION(minInclusive=0.9) vs None ; dataType user-set.Stress strength: IFCPRESSUREMEASURE vs IFCREAL ; mapped 'Span' -> Pset_BeamCommon.Span | mapped to IFC vocabulary where the gold keeps a user-defined property; dataType chosen differently; value differs |
| row-0138 | NL | failing | over_strict+under_strict | `cand:full:IFCTRANSFORMER` | missing Pset_EnergyRequirements.EnergyConversionEfficiency ; extra Pset_TransformerTypeCommon.SecondaryCurrentType | requirement missing; requirement added |
| row-0140 | NL | failing | over_strict+under_strict | `cand:full:IFCFAN` | mapped 'NominalAirFlowRate' -> Pset_FanTypeCommon.NominalAirFlowRate | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0144 | NL | failing | over_strict+under_strict | `cand:edge:0:minInclusive` | mapped 'NominalAirFlowRate' -> Pset_FanTypeCommon.NominalAirFlowRate | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0154 | NL | failing | over_strict+under_strict | `cand:full:IFCPUMP` | dataType user-set.Rated discharge rate: IFCMASSFLOWRATEMEASURE vs IFCVOLUMETRICFLOWRATEMEASURE ; mapped 'Rated voltage' -> Pset_ElectricalDeviceCommon.RatedVoltage | mapped to IFC vocabulary where the gold keeps a user-defined property; dataType chosen differently |
| row-0156 | CSV | failing | over_strict+under_strict | `cand:full:IFCPUMP` | dataType user-set.Water supply information: IFCMASSFLOWRATEMEASURE vs IFCVOLUMETRICFLOWRATEMEASURE | dataType chosen differently |
| row-0160 | CSV | failing | under_strict | `cand:full:IFCSPACE` | value Pset_SpaceCommon.HandicapAccessible: false vs None | value differs |
| row-0162 | CSV | failing | over_strict+under_strict | `cand:altvalue:2:1` | mapped 'Height' -> Qto_DoorBaseQuantities.Height ; mapped 'Width' -> Qto_DoorBaseQuantities.Width ; missing user-set.Material ; extra material  | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0164 | CSV | failing | over_strict+under_strict | `cand:full:IFCSTAIRFLIGHT` | mapped 'Manufacturer' -> Pset_ManufacturerTypeInformation.Manufacturer ; missing Stair tread.Price ; extra user-set.Price | mapped to IFC vocabulary where the gold keeps a user-defined property |
| row-0166 | CSV | unverified | witness_unverified | `` | missing Pset_Risk.AffectsSurroundings | unverifiable under ifctester 0.8.5 (see caveats) |

**The request checks on held-out requests** (`h6_ishigaki_request_checks.csv`). The checks were
designed on the dev set, where they never fired for Sonnet. On Ishigaki they fire:

- **Sonnet:** fired in 4 stage-1 and 4 stage-2 item-runs. In 5 cases they named a property the gold
  constrains, and each time the final file then differs from the gold there. Example: row-0160's
  "No" → `HandicapAccessible = false` was rejected as a Boolean pinned without a directive. The
  model dropped the value, and that is the item's only difference from the gold.
- **Opus:** fired in 12 stage-1 and 3 stage-2 item-runs, on 17 properties the gold constrains. In
  7 of them the check *helped*: it rejected a unit-converted number (0.85 for "850 mm", 2800 for
  "2.8 kW"), Opus returned to the request's literal number, and that is what the gold uses. In the
  other 10 Opus dropped or changed the constraint.

So the checks enforce "numbers as the request writes them". That matches Ishigaki's convention
for magnitudes, but not for dates, for derived numbers (1/20, 0.0125) or for Yes/No Booleans.
That is a property of the checks the dev set could not show.

## 3. Stage C: the other single-turn items, and Run 10

The scorer now handles several specifications, attribute/property facets in applicability, and
entity patterns (`IFC.*`). This unlocks the 20 single-turn non-native items:

- 7 with several specifications and entity-only applicability;
- 13 with attribute or property facets in applicability.

The 22 multi-turn items (editing an earlier IDS) were skipped, as the handover allows. On the
witness models the rebuilt references behave like the gold on 19 of 20; row-0008 is the
`pattern=true` Boolean case again.

| | Sonnet (Run 9) | Opus (Run 9) | Sonnet, Run 10 |
| --- | --- | --- | --- |
| items run / ok | 20 / 20 | 20 / 20 | 20 / 20 |
| S1 strict, standard = probe | 1/19 = 0.053 [0.00, 0.16] | 1/19 = 0.053 [0.00, 0.16] | **7/19 = 0.368 [0.16, 0.58]** |
| FacetF1 their way (with / without version) | 0.544 / 0.564 | 0.469 / 0.484 | 0.614 / 0.642 |
| NL / CSV S1 | 0.10 / 0.00 | 0.10 / 0.00 | 0.30 / 0.44 |
| official audit, full / structure only | 0/20 / 20/20 | 0/20 / 20/20 | 0/20 / 20/20 |
| full audit without the two serializer defaults | 18/20 | 16/20 | 19/20 |

In Run 9, 14 of Sonnet's 18 failures differ in applicability. The cause: the generator's
`Applicability` held only an entity. "Rooms named Room A … D" or "slabs with slope under 0.05"
could not be expressed, and every candidate collapsed to entity-only specifications.

**Run 10** is that one change, made after looking at this result. `Applicability` gains
`attributes` / `properties` (and partOf / classifications / materials). The serializer writes them
without cardinality, as the XSD requires. Server rule 5 adds one sentence saying when to use them.
All of stage 1, stage 2 and the dev set were rerun with Sonnet:

- **Stage 2:** gains 6 items, loses none: rows 0020/0022 (rooms A–D by Name), 0034, 0060, 0072 and
  0120, all selected by attribute.
- **Stage 1:** unchanged (12/38); two items gained and two lost, which is sampling variation.
- **Dev set:** unchanged except IDS4ALL#2, which is exact again; no dev file uses the new facets.

The stage-2 Run 10 number is not held-out clean: the change was made because of these items. The
stage-1 numbers are.

## 4. Opus against Sonnet, paired by item

- **Dev set (Run 8):** the same verdict on every item in every scoring.
- **Ishigaki stage 1 (Run 9):** Opus better on 1 item (row-0088) and worse on 6 (rows 0004, 0038,
  0064, 0070, 0122, 0152). Its FacetF1 is lower on 16 items and higher on 2, a mean difference of
  −0.17. The causes are visible in `h5`:
  - Opus drops the dataType on user-defined properties: 37 dataType differences, against 15 for
    Sonnet. It follows the server rule "omit dataType if ifc_type is missing" literally, and a
    user-defined property never has a graph type.
  - It rewrites the request's words into CamelCase ("EffectiveWidth" for "effective width"),
    against the prompt.

  Sonnet types user-defined properties sensibly and keeps the wording. The dataType rule was
  written for standard properties; on this benchmark it costs the model that follows instructions
  more literally.
- **Ishigaki stage 2 (Run 9):** no difference in S1 (1/19 each). Opus has the lower FacetF1.

## 5. Caveats

- **The entity is given in the prompt** ("Applies to: IFCPAVEMENT"), as for the dev set.
  Ishigaki's own task gives the model none, and "sidewalk → IFCPAVEMENT" is part of what it tests.
- **The property-set convention is given**, as the benchmark's own task instruction gives it.
- **The request's IFC version is dropped.** The harness message always says "Target schema:
  IFC4X3_ADD2", and both models declared IFC4X3_ADD2 everywhere. Only 14 of the 41 stage-1 gold
  files declare that version alone, so the with-version FacetF1 is depressed by construction.
  Version does not matter for S1: the witness is IFC4X3_ADD2, and execution ignores the version.
- **Ishigaki barely tests the knowledge graph.** 9 of 110 stage-1 property facets use a standard
  set. Where the system's purpose shows — mapping to IFC vocabulary — the benchmark counts it as a
  failure.
- **One repeat per model and stage.** Run 7 showed Sonnet to be almost deterministic on the dev
  set, which may not hold here (stage 1: two flips each way between Run 9 and Run 10).
- **The scorer gained support for Ishigaki shapes** (lookahead patterns, entity patterns, several
  specifications, applicability facets, partOf). Each is tested, and none changes any dev item.
  The verdict code (`compare` / `graded` / `verdicts`) is unchanged.

## 6. Problems hit and what changed

1. **ifctester 0.8.5 raises on `^(?!(Pset_|Qto_)).+`** (a lookahead, not XSD regex) as soon as an
   applicable element has a property set. A pattern that XSD regex rejects is now read as a Python
   regex (`score._translate_pattern`). On the dev models the gold had executed by accident: no
   pavement, nothing applicable.
2. **`facet_target` never extracted a partOf's whole**, because it read `<entity>` instead of
   `<entity><name>`. Fixed, together with the relation; no existing reference or run had a partOf.
   The witness can now build partOf.
3. **A running generation loads `aec_kg` per item**, through a fresh MCP server. No generator file
   was edited while a run was in flight; Run 10's patch waited for Opus to finish.
4. **The first Run 8 scoring refused**, because the run directory had no graph snapshot. Snapshots
   were written from the updated graph into the new run directories only.
5. **The replay** now covers Runs 5–8 and 10 (`e4` and `e5`). Run 10 shows up as "run1" because
   the summary groups runs by their first four characters. 8 Run 6/7 calls that were rejected at the
   time (partOf, classifications) now pass the document model; no accepted-document statistic
   changes.
6. **Attribution:** commits carry `Co-Authored-By: Claude Opus 5.5`, the model that ran this
   session, not the Fable line the handover suggests.
7. **The audit tool's package id:** the handover's `dotnet tool install -g ids-tool` finds no
   package. The tool is published as `ids-tool.commandline` (author Claudio Benghi, tags IDS and
   buildingSmart) and provides the `ids-tool` command. Its `errorcode` command describes exit
   codes, not message numbers, so the table above quotes the messages themselves.

Files: `eval/ishigaki_bench/{convert,analysis,failures,check_firings,audit}.py`,
`eval/ishigaki_bench/spec_tasks_en.jsonl`, `item_lists/`, `eval/claude_system_prompt_ishigaki.md`,
`eval/annotations/cardinality.jsonl`, `tests/test_v9_devset_causes.py` (30 tests),
`eval/reports/v9/h1`–`h7`, the regenerated `e2`, `e4`, `e5`, `p1` and `p2`, and `README.md` §C.
Runs (not committed): `eval/runs/run7-claude-rep*-rescored-v9b`, `run8-{claude,opus}-rep1`,
`run9-ishigaki{,-opus}-rep1{,-s2}`, `run10-claude-rep1`, `run10-ishigaki-rep1{,-s2}`.
