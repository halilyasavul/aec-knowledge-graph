"""
Re-ingest saved UCKS entity YAML files into Neo4j.

Reads every YAML in data/ucks_entities/**/, validates it against EntityDef,
and ingests it into the graph. Use after rebuilding the database (e.g. a new
Aura instance) to restore user-defined entities without redefining them.

Usage:
    python reingest_ucks.py            # validate + ingest into Neo4j
    python reingest_ucks.py --dry-run  # validate YAMLs only, no DB needed
"""

import argparse
import logging
import sys

import yaml

from ucks_models import EntityDef
from ucks_pipeline import UCKS_OUTPUT_DIR, ingest_entity_to_neo4j

logger = logging.getLogger(__name__)


def load_entity_yaml(path) -> EntityDef:
    """Load a saved UCKS YAML file and rebuild the flat EntityDef."""
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    entity = dict(doc.get("entity", {}))
    entity.setdefault("sector", doc.get("sector"))
    entity.setdefault("domain", doc.get("domain"))
    return EntityDef(**entity)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-ingest saved UCKS YAML entities into Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Validate YAMLs without touching Neo4j")
    args = parser.parse_args()

    yaml_files = sorted(UCKS_OUTPUT_DIR.rglob("*.yaml"))
    if not yaml_files:
        logger.warning("No YAML files found under %s", UCKS_OUTPUT_DIR)
        return

    logger.info("Found %d UCKS entity file(s).", len(yaml_files))

    failures = 0
    for path in yaml_files:
        try:
            entity = load_entity_yaml(path)
        except Exception as e:
            failures += 1
            logger.error("Invalid entity YAML %s: %s", path, e)
            continue

        if args.dry_run:
            logger.info("OK (dry run): %s -> %s", path.name, entity.id)
            continue

        stats = ingest_entity_to_neo4j(entity)
        logger.info(
            "Ingested %s: %d nodes, %d relationships",
            entity.id, stats["nodes_created"], stats["relationships_created"],
        )

    if failures:
        logger.error("%d file(s) failed validation.", failures)
        sys.exit(1)
    logger.info("Done.")


if __name__ == "__main__":
    main()
