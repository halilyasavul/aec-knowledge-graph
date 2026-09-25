# Determinacy draft — please review

One line per target facet that the draft marks **undetermined**.
`scope=facet` drops the requirement; `scope=value` keeps the requirement but drops its value constraint.
Edit/delete lines in `determinacy.draft.jsonl`, then save it as `determinacy.jsonl`.

## IDS4ALL-Template_Example specifications.ids#2  (9 requirements)
request: A slab is a structural component that normally closes off a room horizontally. Slabs also include the landing for stairs and ramps (this is a separate defined type of the slab element class and can be found on the IFC website under ‘IfcSlabTypeEnum’). According to ÖNORM A 6241-2 Annex A, a slab is a...

- facet 1 — property Pset_SlabCommon.LoadBearing — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 2 — property Pset_SlabCommon.Compartmentation — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 3 — property Pset_SlabCommon.SurfaceSpreadOfFlame — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 4 — property Pset_SlabCommon.ThermalTransmittance — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 5 — property Pset_SlabCommon.IsExternal — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 6 — property Pset_SlabCommon.AcousticRating — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 7 — property Pset_SlabCommon.Combustible — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 8 — material CONCRETE — **facet** — requirement has no description in the source IDS, so the request never mentions it

## IDS4ALL-Template_Example specifications.ids#4  (1 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_WallCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## IDS4ALL-Template_Example specifications.ids#5  (1 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_WallCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## IDS4ALL-Template_Example specifications.ids#14  (1 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_SlabCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## IDS4ALL-Template_Example specifications.ids#15  (1 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_SlabCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## IDS4ALL-Template_Example specifications.ids#16  (1 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_SlabCommon.FireRating — **value** — pattern 'REI\\s[0-9]{2,3}' is not derivable from the request text

## IDS4ALL-Template_Example specifications.ids#17  (5 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_WallCommon.Combustible — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 1 — property Pset_WallCommon.FireRating — **value** — exact value 'REI 90' is not stated in the request
- facet 2 — property Pset_WallCommon.IsExternal — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 3 — property Pset_WallCommon.LoadBearing — **facet** — requirement has no description in the source IDS, so the request never mentions it
- facet 4 — property Pset_WallCommon.ThermalTransmittance — **facet** — requirement has no description in the source IDS, so the request never mentions it

## IDS4ALL-Template_Example specifications.ids#18  (2 requirements)
request: FireRating: Fire resistance class according to national or regional fire protection regulations....

- facet 0 — property Pset_WallCommon.FireRating — **value** — exact value 'REI 120' is not stated in the request
- facet 1 — property Pset_WallCommon.LoadBearing — **facet** — requirement has no description in the source IDS, so the request never mentions it

## IDS_ArcDox.ids#4  (5 requirements)
request: Address  / Town  / Region  / Country  / Postal Code...

- facet 3 — attribute Country — **value** — exact value 'Ireland' is not stated in the request

## IDS_oma_input.ids#2  (2 requirements)
request: Storey name/number...

- facet 0 — attribute Name — **value** — pattern '[\\S\\s]+[\\S]+' is not derivable from the request text
- facet 1 — property Pset_BuildingStoreyCommon.ElevationOfFFLRelative — **facet** — requirement has no description in the source IDS, so the request never mentions it

## IDS_oma_input.ids#10  (5 requirements)
request: The type of ramp  / Descriptive name  / Indication that this object is designed to be accessible by the handicapped  / Required sloping angle of the object - relative to horizontal  / Indication whether this object is designed to serve as an exit in the case of fire...

- facet 0 — attribute PredefinedType — **value** — allowed-value list not stated: 0/8 values appear in the request (none)
- facet 1 — attribute Name — **value** — pattern '[\\S\\s]+[\\S]+' is not derivable from the request text

## IDS_oma_input.ids#13  (1 requirements)
request: The type of alarm...

- facet 0 — attribute PredefinedType — **value** — allowed-value list not stated: 0/8 values appear in the request (none)

## NL_BIM_Basis_ILS_v2.ids#1  (1 requirements)
request: Verdiepingsnaam moet beginnen met niveau-aanduiding...

- facet 0 — attribute Name — **value** — pattern '-?\\d{2}\\s.*' is not derivable from the request text

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#46  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_BeamCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#47  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_BeamCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#57  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_RoofCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#58  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_RoofCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#61  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_SlabCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#62  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_SlabCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#71  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_WindowCommon.FireRating — **value** — allowed-value list not stated: 0/3 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#77  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_PlateCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#78  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_PlateCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#82  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_RampCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#83  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_RampCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#84  (1 requirements)
request: Erforderlicher Neigungswinkel der Rampe - relativ zur Horizontalen (0,0 Grad). Erforderliche maximale Neigung des Durchgangs gemäß der geltenden Bauordnung oder zusätzlichen Anforderungen. Der Winkel wird in IDS in Radiant angegeben....

- facet 0 — property Pset_RampCommon.RequiredSlope — **value** — bound {'maxInclusive': ['0.06']} not stated in the request (no number and no comparative wording)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#128  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_ColumnCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#129  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_ColumnCommon.FireRating — **value** — allowed-value list not stated: 0/7 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#132  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_StairCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#133  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_StairCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#155  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_WallCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)

## Requirements-openBIM-building-permit-City-of-Vienna-extended_Specifications.ids#156  (1 requirements)
request: Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung....

- facet 0 — property Pset_WallCommon.FireRating — **value** — allowed-value list not stated: 0/12 values appear in the request (none)
