# Determinacy annotations (machine-made, not human-reviewed)

Items: 47. Target facets: 82.

- pass A (text heuristics) marked 45 facets undetermined
- pass B (final: mechanical value rule + author's reading) marked 45: {'facet': 14, 'value': 31}
- the passes agree on 82/82 facets (100%)

`scope=facet` drops the requirement from the relaxed reference; `scope=value` keeps the
requirement and drops its value constraint.

## Appendix: disagreements

(none)

## Pass B, undetermined facets

- IDS4ALL-Template_Example specifications.ids#2 facet 1 — property Pset_SlabCommon.LoadBearing — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 2 — property Pset_SlabCommon.Compartmentation — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 3 — property Pset_SlabCommon.SurfaceSpreadOfFlame — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 4 — property Pset_SlabCommon.ThermalTransmittance — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 5 — property Pset_SlabCommon.IsExternal — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 6 — property Pset_SlabCommon.AcousticRating — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 7 — property Pset_SlabCommon.Combustible — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#2 facet 8 — material CONCRETE — **facet** [B-read] — the request only defines what a slab is; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#4 facet 0 — property Pset_WallCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- IDS4ALL-Template_Example specifications.ids#5 facet 0 — property Pset_WallCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- IDS4ALL-Template_Example specifications.ids#14 facet 0 — property Pset_SlabCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- IDS4ALL-Template_Example specifications.ids#15 facet 0 — property Pset_SlabCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- IDS4ALL-Template_Example specifications.ids#16 facet 0 — property Pset_SlabCommon.FireRating — **value** [A-heuristic] — pattern 'REI\\s[0-9]{2,3}' is not derivable from the request text
- IDS4ALL-Template_Example specifications.ids#17 facet 0 — property Pset_WallCommon.Combustible — **facet** [B-read] — the request states only the fire-rating requirement; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#17 facet 1 — property Pset_WallCommon.FireRating — **value** [A-heuristic] — exact value 'REI 90' is not stated in the request
- IDS4ALL-Template_Example specifications.ids#17 facet 2 — property Pset_WallCommon.IsExternal — **facet** [B-read] — the request states only the fire-rating requirement; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#17 facet 3 — property Pset_WallCommon.LoadBearing — **facet** [B-read] — the request states only the fire-rating requirement; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#17 facet 4 — property Pset_WallCommon.ThermalTransmittance — **facet** [B-read] — the request states only the fire-rating requirement; this property is never mentioned
- IDS4ALL-Template_Example specifications.ids#18 facet 0 — property Pset_WallCommon.FireRating — **value** [A-heuristic] — exact value 'REI 120' is not stated in the request
- IDS4ALL-Template_Example specifications.ids#18 facet 1 — property Pset_WallCommon.LoadBearing — **facet** [B-read] — the request states only the fire-rating requirement; load bearing is never mentioned
- IDS_ArcDox.ids#4 facet 3 — attribute Country — **value** [A-heuristic] — exact value 'Ireland' is not stated in the request
- IDS_oma_input.ids#2 facet 0 — attribute Name — **value** [A-heuristic] — pattern '[\\S\\s]+[\\S]+' is not derivable from the request text
- IDS_oma_input.ids#2 facet 1 — property Pset_BuildingStoreyCommon.ElevationOfFFLRelative — **facet** [B-read] — the request asks for the storey name/number; floor elevation is never mentioned
- IDS_oma_input.ids#10 facet 0 — attribute PredefinedType — **value** [B-mechanical] — 8 of 8 values are neither IFC allowed values nor in the request (HALF_TURN_RAMP, QUARTER_TURN_RAMP, SPIRAL_RAMP, STRAIGHT_RUN_RAMP)
- IDS_oma_input.ids#10 facet 1 — attribute Name — **value** [A-heuristic] — pattern '[\\S\\s]+[\\S]+' is not derivable from the request text
- IDS_oma_input.ids#13 facet 0 — attribute PredefinedType — **value** [B-mechanical] — 8 of 8 values are neither IFC allowed values nor in the request (BELL, BREAKGLASSBUTTON, LIGHT, MANUALPULLBOX)
- NL_BIM_Basis_ILS_v2.ids#1 facet 0 — attribute Name — **value** [A-heuristic] — pattern '-?\\d{2}\\s.*' is not derivable from the request text
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#46 facet 0 — property Pset_BeamCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#47 facet 0 — property Pset_BeamCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#57 facet 0 — property Pset_RoofCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#58 facet 0 — property Pset_RoofCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#61 facet 0 — property Pset_SlabCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#62 facet 0 — property Pset_SlabCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#71 facet 0 — property Pset_WindowCommon.FireRating — **value** [B-mechanical] — 3 of 3 values are neither IFC allowed values nor in the request (EI2 30-C-Sm, EI2 60-C-Sm, EI2 90-C-Sm)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#77 facet 0 — property Pset_PlateCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#78 facet 0 — property Pset_PlateCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#82 facet 0 — property Pset_RampCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#83 facet 0 — property Pset_RampCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#84 facet 0 — property Pset_RampCommon.RequiredSlope — **value** [A-heuristic] — bound {'maxInclusive': ['0.06']} not stated in the request (no number and no comparative wording)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#128 facet 0 — property Pset_ColumnCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#129 facet 0 — property Pset_ColumnCommon.FireRating — **value** [B-mechanical] — 7 of 7 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#132 facet 0 — property Pset_StairCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#133 facet 0 — property Pset_StairCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#155 facet 0 — property Pset_WallCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, R 30, R 60)
- Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#156 facet 0 — property Pset_WallCommon.FireRating — **value** [B-mechanical] — 12 of 12 values are neither IFC allowed values nor in the request (ND, NE, EI 30, EI 60)