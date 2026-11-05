"""
Deterministic IDS XML serializer.

Converts an ``IdsDocument`` Pydantic model into a valid IDS XML string.
No LLM involvement — pure code.
"""

from __future__ import annotations

import functools
import xml.etree.ElementTree as ET

from aec_kg.ids.models import (
    Applicability,
    AttributeFacet,
    ClassificationFacet,
    EntityFacet,
    IdsDocument,
    IdsRestriction,
    IdsValue,
    MaterialFacet,
    PartOfFacet,
    PropertyFacet,
    Requirements,
)

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

IDS_NS = "http://standards.buildingsmart.org/IDS"
XS_NS = "http://www.w3.org/2001/XMLSchema"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# Register prefixes so the output uses ids: / xs: / xsi: instead of ns0/ns1/ns2
ET.register_namespace("ids", IDS_NS)
ET.register_namespace("xs", XS_NS)
ET.register_namespace("xsi", XSI_NS)


def _ids(tag: str) -> str:
    """Return a fully-qualified IDS-namespace tag."""
    return f"{{{IDS_NS}}}{tag}"


def _xs(tag: str) -> str:
    """Return a fully-qualified XS-namespace tag."""
    return f"{{{XS_NS}}}{tag}"


# ---------------------------------------------------------------------------
# Value builders
# ---------------------------------------------------------------------------

# The XSD base of a restriction on a property value follows the property's dataType: the EXPRESS
# underlying type (REAL/NUMBER -> xs:double, INTEGER -> xs:integer, BOOLEAN -> xs:boolean, else
# xs:string), except the date/time and URI types, which IDS gives their own XSD types. This is the
# table buildingSMART's ids-tool audits against (error 303), for all 132 IFC 4.3 defined types.
_XSD_OF_EXPRESS = {"real": "xs:double", "number": "xs:double", "integer": "xs:integer", "boolean": "xs:boolean"}
_XSD_OWN_TYPE = {"IFCDATE": "xs:date", "IFCDATETIME": "xs:dateTime", "IFCDURATION": "xs:duration",
                 "IFCTIME": "xs:time", "IFCURIREFERENCE": "xs:anyURI"}
_BOUNDS = ("minInclusive", "maxInclusive", "minExclusive", "maxExclusive")


@functools.lru_cache(maxsize=None)
def xsd_base(data_type: str | None) -> str | None:
    """XSD base type for values of an IFC data type (e.g. IFCLENGTHMEASURE -> xs:double);
    None when the name is not an IFC defined type."""
    if not data_type:
        return None
    t = data_type.upper()
    if t in _XSD_OWN_TYPE:
        return _XSD_OWN_TYPE[t]
    import ifcopenshell.ifcopenshell_wrapper as W
    for schema in ("IFC4X3_ADD2", "IFC4", "IFC2X3"):
        try:
            d = W.schema_by_name(schema).declaration_by_name(t)
        except RuntimeError:
            continue
        if not isinstance(d, W.type_declaration):
            return None
        while isinstance(d, (W.type_declaration, W.named_type)):
            d = d.declared_type()
        return _XSD_OF_EXPRESS.get(d.declared_type(), "xs:string") if isinstance(d, W.simple_type) else "xs:string"
    return None


def _build_ids_value(parent: ET.Element, tag: str, value: IdsValue, data_type: str | None = None) -> None:
    """Append an IDS value element (simpleValue or xs:restriction) under *parent*."""
    wrapper = ET.SubElement(parent, _ids(tag))

    if value.simpleValue is not None:
        sv = ET.SubElement(wrapper, _ids("simpleValue"))
        sv.text = value.simpleValue
    elif value.restriction is not None:
        _build_restriction(wrapper, value.restriction, data_type)


def _restriction_base(r: IdsRestriction, data_type: str | None) -> str:
    """A base the document states wins; otherwise the dataType's XSD type; otherwise xs:double
    for numeric bounds, which an xs:string restriction cannot carry; otherwise xs:string."""
    if "base" in r.model_fields_set:
        return r.base
    return xsd_base(data_type) or ("xs:double" if any(getattr(r, b) is not None for b in _BOUNDS) else r.base)


def _build_restriction(parent: ET.Element, r: IdsRestriction, data_type: str | None = None) -> None:
    """Build an ``<xs:restriction base="...">`` element."""
    restriction = ET.SubElement(parent, _xs("restriction"))
    restriction.set("base", _restriction_base(r, data_type))

    if r.enumerations:
        for val in r.enumerations:
            enum_el = ET.SubElement(restriction, _xs("enumeration"))
            enum_el.set("value", val)

    if r.pattern is not None:
        pat = ET.SubElement(restriction, _xs("pattern"))
        pat.set("value", r.pattern)

    if r.minInclusive is not None:
        el = ET.SubElement(restriction, _xs("minInclusive"))
        el.set("value", r.minInclusive)

    if r.maxInclusive is not None:
        el = ET.SubElement(restriction, _xs("maxInclusive"))
        el.set("value", r.maxInclusive)

    if r.minExclusive is not None:
        el = ET.SubElement(restriction, _xs("minExclusive"))
        el.set("value", r.minExclusive)

    if r.maxExclusive is not None:
        el = ET.SubElement(restriction, _xs("maxExclusive"))
        el.set("value", r.maxExclusive)


# ---------------------------------------------------------------------------
# Facet builders
# ---------------------------------------------------------------------------

def _build_entity(parent: ET.Element, facet: EntityFacet) -> None:
    entity = ET.SubElement(parent, _ids("entity"))
    _build_ids_value(entity, "name", facet.name)
    if facet.predefinedType is not None:
        _build_ids_value(entity, "predefinedType", facet.predefinedType)


def _build_property(
    parent: ET.Element, facet: PropertyFacet, is_requirement: bool
) -> None:
    prop = ET.SubElement(parent, _ids("property"))
    if facet.dataType:
        prop.set("dataType", facet.dataType)
    if is_requirement and facet.cardinality != "required":
        prop.set("cardinality", facet.cardinality)
    if is_requirement and facet.instructions:
        prop.set("instructions", facet.instructions)

    _build_ids_value(prop, "propertySet", facet.propertySet)
    _build_ids_value(prop, "baseName", facet.baseName)
    if facet.value is not None:
        _build_ids_value(prop, "value", facet.value, facet.dataType)


def _build_attribute(
    parent: ET.Element, facet: AttributeFacet, is_requirement: bool
) -> None:
    attr = ET.SubElement(parent, _ids("attribute"))
    if is_requirement and facet.cardinality != "required":
        attr.set("cardinality", facet.cardinality)
    if is_requirement and facet.instructions:
        attr.set("instructions", facet.instructions)

    _build_ids_value(attr, "name", facet.name)
    if facet.value is not None:
        _build_ids_value(attr, "value", facet.value)


def _set_requirement_attrs(el: ET.Element, facet, is_requirement: bool = True) -> None:
    if not is_requirement:                            # applicability facets have neither attribute
        return
    if facet.cardinality != "required":
        el.set("cardinality", facet.cardinality)
    if facet.instructions:
        el.set("instructions", facet.instructions)


def _build_part_of(parent: ET.Element, facet: PartOfFacet, is_requirement: bool = True) -> None:
    el = ET.SubElement(parent, _ids("partOf"))
    if facet.relation:
        el.set("relation", facet.relation)
    _set_requirement_attrs(el, facet, is_requirement)
    _build_entity(el, facet.entity)


def _build_classification(parent: ET.Element, facet: ClassificationFacet, is_requirement: bool = True) -> None:
    el = ET.SubElement(parent, _ids("classification"))
    _set_requirement_attrs(el, facet, is_requirement)
    if facet.value is not None:                       # the XSD orders value before system
        _build_ids_value(el, "value", facet.value)
    _build_ids_value(el, "system", facet.system)


def _build_material(parent: ET.Element, facet: MaterialFacet, is_requirement: bool = True) -> None:
    el = ET.SubElement(parent, _ids("material"))
    _set_requirement_attrs(el, facet, is_requirement)
    if facet.value is not None:
        _build_ids_value(el, "value", facet.value)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_applicability(parent: ET.Element, app: Applicability) -> None:
    el = ET.SubElement(parent, _ids("applicability"))
    # Unstated, the XSD default is exactly one element [1..1], which the IDS implementation
    # agreements do not allow (ids-tool error 301). Default to optional [0..unbounded]; a stated
    # minOccurs keeps maxOccurs unbounded (required is [1..unbounded]).
    el.set("minOccurs", str(app.minOccurs if app.minOccurs is not None else 0))
    el.set("maxOccurs", str(app.maxOccurs if app.maxOccurs is not None else "unbounded"))

    # XSD order: entity, partOf, classification, attribute, property, material
    if app.entity is not None:
        _build_entity(el, app.entity)
    for part in app.partOf or ():
        _build_part_of(el, part, is_requirement=False)
    for cls in app.classifications or ():
        _build_classification(el, cls, is_requirement=False)
    for attr in app.attributes or ():
        _build_attribute(el, attr, is_requirement=False)
    for prop in app.properties or ():
        _build_property(el, prop, is_requirement=False)
    for mat in app.materials or ():
        _build_material(el, mat, is_requirement=False)


def _build_requirements(parent: ET.Element, req: Requirements) -> None:
    el = ET.SubElement(parent, _ids("requirements"))

    # XSD order: entity, partOf, classification, attribute, property, material
    for part in req.partOf or ():
        _build_part_of(el, part)

    for cls in req.classifications or ():
        _build_classification(el, cls)

    if req.attributes:
        for attr in req.attributes:
            _build_attribute(el, attr, is_requirement=True)

    if req.properties:
        for prop in req.properties:
            _build_property(el, prop, is_requirement=True)

    for mat in req.materials or ():
        _build_material(el, mat)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def serialize_ids(doc: IdsDocument) -> str:
    """
    Serialize an ``IdsDocument`` to a valid IDS XML string.

    Returns:
        A UTF-8 XML string with ``<?xml ...?>`` declaration.
    """
    root = ET.Element(_ids("ids"))
    root.set(f"{{{XSI_NS}}}schemaLocation",
             f"{IDS_NS} http://standards.buildingsmart.org/IDS/1.0/ids.xsd")

    # --- info ---
    info_el = ET.SubElement(root, _ids("info"))
    title_el = ET.SubElement(info_el, _ids("title"))
    title_el.text = doc.info.title

    for field_name in ("copyright", "version", "description", "author",
                       "date", "purpose", "milestone"):
        val = getattr(doc.info, field_name)
        if val is not None:
            child = ET.SubElement(info_el, _ids(field_name))
            child.text = val

    # --- specifications ---
    specs_el = ET.SubElement(root, _ids("specifications"))

    for spec in doc.specifications:
        spec_el = ET.SubElement(specs_el, _ids("specification"))
        spec_el.set("name", spec.name)
        spec_el.set("ifcVersion", spec.ifcVersion)
        if spec.description:
            spec_el.set("description", spec.description)
        if spec.instructions:
            spec_el.set("instructions", spec.instructions)

        _build_applicability(spec_el, spec.applicability)

        if spec.requirements is not None:
            _build_requirements(spec_el, spec.requirements)

    # Serialize to string
    ET.indent(root, space="\t")
    tree = ET.ElementTree(root)
    # Use xml_declaration with encoding
    import io
    buf = io.BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue().decode("UTF-8")
