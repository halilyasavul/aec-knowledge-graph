# Data Directory

The knowledge graph is built from official buildingSMART schema files. These
are **not redistributed** in this repository — buildingSMART requires
account-based access for bSDD exports, and the content is their copyright.
Download them yourself (free) and place them here before running ingestion.

## Required files

| File | Source | How to get it |
|------|--------|---------------|
| `ifc-4.3.json` | [bSDD](https://search.bsdd.buildingsmart.org/) | Create a free bSDD account, open the **IFC** dictionary (version 4.3), and export the full dictionary as JSON. Save it as `data/ifc-4.3.json` (~60 MB). |
| `IFC4X3_ADD2.exp.txt` | [buildingSMART IFC specifications](https://technical.buildingsmart.org/standards/ifc/ifc-schema-specifications/) | Download the **IFC 4.3 ADD2** EXPRESS schema (`.exp`). Save it as `data/IFC4X3_ADD2.exp.txt`. |

## Included files

| File | Purpose |
|------|---------|
| `ids.xsd` | IDS 1.0 XML Schema from the [buildingSMART IDS repository](https://github.com/buildingSMART/IDS), used to validate generated IDS specifications. |
| `ucks_entities/**/*.yaml` | Example UCKS (Universal Civil Knowledge Schema) entity definitions created through the Define workflow. Re-ingest them with `python reingest_ucks.py`. |

## Generated at runtime

| Path | Purpose |
|------|---------|
| `ids_output/` | IDS XML files generated through the chat interface. |
| `ucks_entities/` | New UCKS entities defined by users are saved here as YAML. |

Everything in this directory except the files listed under "Included files"
is gitignored.
