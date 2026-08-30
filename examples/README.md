# Examples

A walk-through of the main functionality, reproducible after completing the
[installation steps](../README.md#installation-and-setup).

## 1. Query the IFC knowledge graph

```bash
python -m aec_kg.main_orchestrator -q "What property sets does IfcRailing require?"
```

The agent calls `query_class("IfcRailing")` against Neo4j and answers from
the returned graph data — property sets like `Pset_RailingCommon` with their
properties and data types. More query prompts: [prompts_queries.md](prompts_queries.md).

## 2. Define a UCKS entity in natural language

In the web UI's **Define** tab (or the chat), describe a concept:

> Define a bridge pier. It's a vertical support structure that transfers
> deck loads to the foundation. It has height, cross-section shape, number
> of columns, and a design load capacity in kN. It's founded on a foundation
> element and supports bridge decks.

The agent structures this into a validated UCKS entity, saves
[../data/ucks_entities/infrastructure/bridge_pier.yaml](../data/ucks_entities/infrastructure/bridge_pier.yaml),
and ingests it into the graph. More definition prompts:
[prompts_ucks_definition.md](prompts_ucks_definition.md).

## 3. Map a concept to IFC and export an IDS specification

Ask the agent to map a concept to IFC and generate an exchange requirement
(full prompt template: [prompts_ifc_mapping.md](prompts_ifc_mapping.md)):

> Export the railing entity to IFC and generate an IDS specification.

The agent finds the closest IFC class (`IfcRailing`), maps each UCKS
property to IFC property sets, and produces an XSD-validated IDS file.

**Example output:** [sample_output_railing.ids](sample_output_railing.ids) —
a generated IDS 1.0 XML file requiring properties such as MASH compliance
and surface texture on `IFCRAILING` elements, validated against the official
buildingSMART `ids.xsd`.
