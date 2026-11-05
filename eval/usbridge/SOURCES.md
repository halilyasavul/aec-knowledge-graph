# usBridge test set — sources

Local folder: `eval/usbridge/source/` (same path on the workstation: `C:\Users\halil\Documents\ifc-ai\eval\usbridge\source\`).

| File | What | Origin | sha256 (first 16) |
|---|---|---|---|
| `AASHTO_IDM_1st_Edition_2023.pdf` | AASHTO Information Delivery Manual for the Design-to-Construction Data Exchange for Highway Bridges, 1st Edition, Jan 2023, 73 pp. **Generator input** (Section 4 tables, bridge wording, no IFC names). | AASHTO store, https://store.transportation.org/Item/CollectionDetail?ID=241 (copyright AASHTO, "no reproduction") | `403327e53116f7ab` |
| `AASHTO_IDM_Version_2.0_2026-06-11.pdf` | IDM Version 2.0, interim draft for industry use, 11 Jun 2026, 248 pp, author HDR. Ch. 4 = workbook narrative, Ch. 5 = the IDS in human-readable form. **Answer-key side, never input.** | https://www.bimforbridgesus.com/files/Information_Delivery_Manual_for_the_Design-to-Construction_Data_Exchange_for_Highway_Bridges_Version_2.0.pdf | `3c65a22f6c596707` |
| `usBridge_Data_Dictionary_Workbook_Version_2.0.xlsx` | IDM 2.0 Appendix 3. 56 entity tabs: Industry Name → IFC class.PredefinedType → description; property tables (cardinality, data type, enumeration, example); "US B&S Concepts" hierarchy. **Answer key.** | Request form on https://www.bimforbridgesus.com/design-construction-exchange-requirements-highway-bridges.html ("AASHTO BIM for Bridges Resources Survey") → download link by email | `dfd1999a72e886c0` |
| `usBrSpec_General.ids` | IDM 2.0 Appendix 4, 17 specs | same form | `f0aaa31a78bb3d9f` |
| `usBrSpec_SpatialBreakdown.ids` | Appendix 4, 45 specs (Project, Site, Bridge, BridgePart, assemblies, systems) | same form | `3fc4a9f00d900998` |
| `usBrSpec_Classes.ids` | Appendix 4, 146 specs (physical objects: IFC class + PredefinedType → attributes, psets, partOf, classification, material) | same form | `d17f526030c04373` |
| `usBrSpec_PropertySets.ids` | Appendix 4, 130 specs (every pset with its properties, data types, cardinality, enumerations) | same form | `cdf1cdf651a90a59` |
| `usBrSpec_AbV Exclusions.ids` | Appendix 4, 261 "entity must not appear" specs. Not used. | same form | `3b038a70567223fd` |

IDS metadata: author `BIMforBridge@hdrinc.com`, version 2.0, date 2026-05-01, IFC4X3_ADD2, milestone "US Bridge Design-to-Construction".

Online copies of the same dictionary:
- bSDD: `usTransportation/usBridge` (preview) — `https://api.bsdd.buildingsmart.org/api/Dictionary/v1`, `/Classes`, `/Properties`, `/api/Class/v1?Uri=…&IncludeClassProperties=true&IncludeClassRelations=true`. Cache under `eval/usbridge/bsdd/`.
- Programme site: https://www.bimforbridgesus.com/ (TPF-5(372) / TPF-5(523), lead agency Iowa DOT; feedback BIMforBridge@hdrinc.com).

Rights: AASHTO holds the IDM-1 copyright; HDR/AASHTO the 2.0 package; bSDD lists the dictionary as "rights reserved". Use for evaluation; ask before redistributing.
