"""
IDS XML validator — validates generated IDS XML against the IDS XSD schema.

Uses lxml for XSD validation. By default falls back gracefully if lxml is
unavailable or the XSD cannot be loaded (e.g. network issues for imported
schemas). Strict mode — ``strict=True`` or env ``IDS_XSD_STRICT=1`` — raises
instead, so a missing validator can never be mistaken for a passing one.
"""

from __future__ import annotations

import logging
import os

from aec_kg.config import IDS_XSD_PATH

logger = logging.getLogger(__name__)

STRICT = os.getenv("IDS_XSD_STRICT", "").lower() in ("1", "true", "yes")

_schema = None
_schema_load_attempted = False
_schema_load_error: Exception | None = None


class XsdUnavailableError(RuntimeError):
    """Raised in strict mode when the IDS XSD cannot be loaded."""


def _get_schema():
    """Load and cache the compiled XSD schema."""
    global _schema, _schema_load_attempted, _schema_load_error

    if _schema is not None:
        return _schema
    if _schema_load_attempted:
        return None

    _schema_load_attempted = True
    try:
        from lxml import etree

        with open(IDS_XSD_PATH, "rb") as f:
            schema_doc = etree.parse(f)
        _schema = etree.XMLSchema(schema_doc)
        logger.info("IDS XSD schema loaded successfully from %s", IDS_XSD_PATH)
        return _schema
    except Exception as e:
        _schema_load_error = e
        logger.warning(
            "Could not load IDS XSD schema (%s). XSD validation will be skipped. "
            "This may be due to network issues (the XSD imports external schemas).",
            e,
        )
        return None


def validate_ids_xml(xml_string: str, strict: bool | None = None) -> tuple[bool, list[str]]:
    """
    Validate an IDS XML string against the IDS XSD schema.

    Args:
        strict: raise ``XsdUnavailableError`` if the schema cannot be loaded.
            Defaults to the module-level ``STRICT`` (env ``IDS_XSD_STRICT``).

    Returns:
        (is_valid, error_messages) — if the schema couldn't be loaded and
        strict is off, returns (True, []) with a logged warning (optimistic
        fallback).
    """
    if strict is None:
        strict = STRICT
    schema = _get_schema()
    if schema is None:
        if strict:
            raise XsdUnavailableError(
                f"IDS XSD could not be loaded from {IDS_XSD_PATH}: {_schema_load_error!r}"
            )
        logger.warning("XSD schema not available — skipping validation.")
        return True, []

    try:
        from lxml import etree

        doc = etree.fromstring(xml_string.encode("UTF-8"))
        is_valid = schema.validate(doc)
        errors = [str(e) for e in schema.error_log] if not is_valid else []
        return is_valid, errors
    except Exception as e:
        return False, [f"XML parsing error: {e}"]
