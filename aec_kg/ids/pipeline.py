"""
IDS generation pipeline — orchestrates model validation, XML serialization,
and XSD validation.

Called from ``dispatch_tool()`` in ``main_orchestrator.py`` when the LLM
invokes the ``generate_ids`` tool.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from aec_kg.ids.models import IdsDocument
from aec_kg.ids.request_checks import RequestContext, check_document
from aec_kg.ids.serializer import serialize_ids
from aec_kg.ids.validator import validate_ids_xml

logger = logging.getLogger(__name__)


def generate_ids_from_json(ids_json: dict, ctx: RequestContext | None = None) -> dict:
    """
    Generate an IDS XML file from an intermediate JSON specification.

    Args:
        ids_json: Dict matching the ``IdsDocument`` Pydantic schema.
        ctx: The request the document answers and the property sets looked up so far
            (``aec_kg.ids.request_checks.RequestContext``). With it, content the request
            does not support is rejected like a validation error; without it only the
            offline checks (property-name hygiene) run.

    Returns:
        On success: ``{"success": True, "ids_xml": "...", "spec_count": N}``
        On Pydantic error: ``{"error": "...", "validation_errors": [...]}``
        On request-check error: ``{"error": "...", "request_errors": [...]}``
        On XSD error: ``{"error": "...", "xsd_errors": [...], "ids_xml": "..."}``
    """
    # Step 1: Pydantic validation
    try:
        doc = IdsDocument.model_validate(ids_json)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        logger.warning("IDS Pydantic validation failed: %s", errors)
        out = {
            "error": "Invalid IDS JSON structure. Fix the errors and retry.",
            "validation_errors": errors,
        }
        if any("Extra inputs are not permitted" in e for e in errors):
            out["hint"] = (
                "Unknown keys are rejected so nothing is dropped silently. Shapes: a value is "
                '{"simpleValue": "EXACT"} or {"restriction": {"enumerations": [...]}} or '
                '{"restriction": {"pattern": "regex"}} or a min/max bound; a property is '
                '{"propertySet": {...}, "baseName": {...}, "dataType": "IFCLABEL", "value": {...}}.')
        return out

    # Step 1b: content the request does not support
    problems = check_document(doc, ctx)
    if problems:
        logger.warning("IDS request checks failed: %s", problems)
        return {
            "error": "The specification states things the request does not. Fix each point and retry.",
            "request_errors": problems,
        }

    # Step 2: Serialize to XML
    try:
        xml_string = serialize_ids(doc)
    except Exception as e:
        logger.error("IDS serialization failed: %s", e, exc_info=True)
        return {"error": f"XML serialization failed: {e}"}

    # Step 3: XSD validation
    is_valid, xsd_errors = validate_ids_xml(xml_string)

    if not is_valid:
        logger.warning("IDS XSD validation failed: %s", xsd_errors)
        return {
            "error": "Generated IDS XML failed XSD validation. Review the errors and fix the JSON.",
            "xsd_errors": xsd_errors,
            "ids_xml": xml_string,
        }

    logger.info(
        "IDS generated successfully: %d specification(s)", len(doc.specifications)
    )
    return {
        "success": True,
        "ids_xml": xml_string,
        "spec_count": len(doc.specifications),
    }
