"""
Pydantic models for the IDS (Information Delivery Specification) intermediate
JSON schema.  The LLM produces JSON matching these models; a deterministic
serializer then converts them to IDS XML.
"""

from __future__ import annotations

import collections
import re

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

# How often each guard fired since the last reset. The eval harness reads and resets these;
# a non-zero count in production means the model is still producing that shape.
GUARDS: collections.Counter = collections.Counter()

# Guards can be switched off for ablation (eval/generate.py --no-model-guards). Production
# keeps them on: a silently dropped key is a silently dropped requirement.
GUARDS_ENABLED = True


def set_guards(enabled: bool) -> None:
    """Enable/disable the v5 guards, including 'unknown key is an error'."""
    global GUARDS_ENABLED
    GUARDS_ENABLED = enabled
    for cls in (IdsRestriction, IdsValue, EntityFacet, PropertyFacet, AttributeFacet,
                Applicability, Requirements, Specification, IdsInfo, IdsDocument):
        cls.model_config = ConfigDict(**{**cls.model_config, "extra": "forbid" if enabled else "ignore"})
        cls.model_rebuild(force=True)

# A simpleValue is an exact value. These shapes mean the model meant something else.
_REGEXY = re.compile(r"(^\^)|(\$$)|(\.\*)|(\.\+)|(\[dswDSW])|(\[[^\]]{2,}\])|(\{\d+(,\d*)?\})|(\|)")
_MAX_VALUE_CHARS = 80
_MAX_VALUE_WORDS = 5
# Meta-words that describe the requirement instead of naming a value. "true"/"false"/"none"
# are left out: those are real IFC values.
_PLACEHOLDERS = {"required", "mandatory", "optional", "any", "anyvalue", "any value", "value",
                 "<value>", "tbd", "todo", "n/a", "na", "placeholder", "xxx", "string", "text",
                 "present", "exists", "not empty", "notempty"}


class _Strict(BaseModel):
    """Unknown keys are errors, not silence: a dropped key is a dropped requirement."""
    model_config = ConfigDict(extra="forbid")

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)


def looks_like_pattern(v: str) -> bool:
    return bool(_REGEXY.search(v))


def looks_like_description(v: str) -> bool:
    """Prose, not a value: too long, or a phrase of several words."""
    return len(v) > _MAX_VALUE_CHARS or len(v.split()) >= _MAX_VALUE_WORDS


def looks_like_placeholder(v: str) -> bool:
    """A word about the requirement ("REQUIRED") rather than a value of it."""
    return v.strip().casefold() in _PLACEHOLDERS


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

class IdsRestriction(_Strict):
    """XSD restriction — constrains a value with enumerations, patterns, or ranges."""
    base: str = Field(
        default="xs:string",
        description="XSD base type, e.g. 'xs:string' or 'xs:double'",
    )
    enumerations: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("enumerations", "enum", "enumeration"),
        description="List of allowed values (xs:enumeration)",
    )
    pattern: str | None = Field(
        default=None,
        description="Regex pattern (xs:pattern)",
    )
    minInclusive: str | None = Field(default=None)
    maxInclusive: str | None = Field(default=None)
    minExclusive: str | None = Field(default=None)
    maxExclusive: str | None = Field(default=None)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _not_empty(self) -> "IdsRestriction":
        if GUARDS_ENABLED and not any((self.enumerations, self.pattern, self.minInclusive, self.maxInclusive,
                                      self.minExclusive, self.maxExclusive)):
            GUARDS["empty_restriction_rejected"] += 1
            raise ValueError(
                "restriction has no constraint — an empty restriction accepts nothing. Give "
                "'enumerations' (list of allowed values), 'pattern', or a min/max bound.")
        return self


class IdsValue(_Strict):
    """
    An IDS value — either a simple literal or an XSD restriction.
    Exactly one of ``simpleValue`` or ``restriction`` must be set.
    """
    simpleValue: str | None = Field(
        default=None,
        description="A literal string value",
    )
    restriction: IdsRestriction | None = Field(
        default=None,
        description="An XSD restriction (enumeration, pattern, range)",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data):
        """Accept the unambiguous shapes the model actually produces.

        A bare string, or {"value": "..."}, can only mean an exact value, so read it as
        simpleValue instead of rejecting it. This is coercion, never a silent drop: an
        unknown key whose meaning is not obvious is still an error.
        """
        if isinstance(data, str):
            GUARDS["value_coerced_from_string"] += 1
            return {"simpleValue": data}
        if isinstance(data, dict) and "simpleValue" not in data and "restriction" not in data:
            for alias in ("value", "simple_value", "simplevalue", "name"):
                if alias in data and isinstance(data[alias], str) and len(data) == 1:
                    GUARDS["value_coerced_from_alias"] += 1
                    return {"simpleValue": data[alias]}
        return data

    @model_validator(mode="after")
    def _exactly_one(self) -> "IdsValue":
        has_simple = self.simpleValue is not None
        has_restriction = self.restriction is not None
        if has_simple == has_restriction:
            raise ValueError(
                "Exactly one of 'simpleValue' or 'restriction' must be set, "
                f"got simpleValue={'set' if has_simple else 'unset'}, "
                f"restriction={'set' if has_restriction else 'unset'}"
            )
        if GUARDS_ENABLED and self.simpleValue is not None:
            v = self.simpleValue.strip()
            if looks_like_pattern(v):
                GUARDS["value_looks_like_pattern"] += 1
                raise ValueError(
                    f"simpleValue {v!r} looks like a regular expression. simpleValue is an exact "
                    "value; use {'restriction': {'pattern': '...'}} for a pattern.")
            if looks_like_placeholder(v):
                GUARDS["value_is_placeholder"] += 1
                raise ValueError(
                    f"simpleValue {v!r} states that the property is required, it is not a value of "
                    "the property. Omit 'value' to require the property to be present, or give the "
                    "allowed values via 'restriction'.")
            if looks_like_description(v):
                GUARDS["value_looks_like_description"] += 1
                raise ValueError(
                    f"simpleValue {v[:60]!r}... reads as a description, not a value. Put guidance in "
                    "'instructions'; use 'restriction' for allowed values, or omit value to only "
                    "require the property to be present.")
        return self


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------

def _uppercase_ids_value(value: IdsValue | None) -> None:
    """Uppercase a value in place — IFC entity names and predefined types are
    uppercase by convention, enforced here rather than trusted to the LLM."""
    if value is None:
        return
    if value.simpleValue is not None:
        value.simpleValue = value.simpleValue.upper()
    if value.restriction is not None and value.restriction.enumerations:
        value.restriction.enumerations = [e.upper() for e in value.restriction.enumerations]


class EntityFacet(_Strict):
    """IDS entity facet — filters by IFC entity type."""
    name: IdsValue = Field(description="Entity name, UPPERCASE (e.g. 'IFCWALL')")
    predefinedType: IdsValue | None = Field(
        default=None,
        description="Optional predefined type filter",
    )

    @model_validator(mode="after")
    def _normalize_case(self) -> "EntityFacet":
        _uppercase_ids_value(self.name)
        _uppercase_ids_value(self.predefinedType)
        return self


class PropertyFacet(_Strict):
    """IDS property facet — requires/filters a property."""
    propertySet: IdsValue = Field(description="Property set name (e.g. 'Pset_WallCommon')")
    baseName: IdsValue = Field(description="Property name within the set")
    value: IdsValue | None = Field(default=None, description="Expected value constraint")
    dataType: str | None = Field(
        default=None,
        description="UPPERCASE IFC data type (e.g. 'IFCTEXT', 'IFCBOOLEAN', 'IFCLENGTHMEASURE')",
    )
    cardinality: str = Field(
        default="required",
        description="'required', 'prohibited', or 'optional' (only for requirements)",
    )
    instructions: str | None = Field(default=None)

    @field_validator("dataType")
    @classmethod
    def _uppercase_datatype(cls, v: str | None) -> str | None:
        # IFC data types (IFCLENGTHMEASURE, IFCLABEL, ...) are uppercase by
        # definition — normalize whatever case the LLM produced
        return v.upper() if isinstance(v, str) else v


class AttributeFacet(_Strict):
    """IDS attribute facet — requires/filters an IFC attribute."""
    name: IdsValue = Field(description="Attribute name (e.g. 'Name', 'Description')")
    value: IdsValue | None = Field(default=None, description="Expected value constraint")
    cardinality: str = Field(
        default="required",
        description="'required', 'prohibited', or 'optional' (only for requirements)",
    )
    instructions: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Applicability & Requirements
# ---------------------------------------------------------------------------

class Applicability(_Strict):
    """Defines which IFC objects a specification applies to."""
    entity: EntityFacet | None = Field(default=None)
    minOccurs: int | None = Field(default=None)
    maxOccurs: str | None = Field(
        default=None,
        description="'unbounded' or an integer string",
    )


class Requirements(_Strict):
    """Defines what must/must-not be present on matching objects."""
    properties: list[PropertyFacet] | None = Field(default=None)
    attributes: list[AttributeFacet] | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _accept_list(cls, data):
        """A bare list of facets is unambiguous: propertySet/baseName is a property, name is an
        attribute. Anything else still errors rather than being dropped."""
        if not isinstance(data, list):
            return data
        props, attrs = [], []
        for f in data:
            if not isinstance(f, dict):
                return data
            if "propertySet" in f or "baseName" in f:
                props.append(f)
            elif "name" in f:
                attrs.append(f)
            else:
                return data                      # unknown shape: let the normal error explain
        GUARDS["requirements_coerced_from_list"] += 1
        return {"properties": props or None, "attributes": attrs or None}


# ---------------------------------------------------------------------------
# Specification & Document
# ---------------------------------------------------------------------------

class Specification(_Strict):
    """A single IDS specification (applicability + requirements)."""
    name: str = Field(description="Human-readable specification name")
    ifcVersion: str = Field(
        default="IFC4X3_ADD2",
        description="Space-separated IFC versions (e.g. 'IFC4X3_ADD2', 'IFC2X3 IFC4')",
    )

    @field_validator("ifcVersion")
    @classmethod
    def _uppercase_ifc_version(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v
    description: str | None = Field(default=None)
    instructions: str | None = Field(default=None)
    applicability: Applicability
    requirements: Requirements | None = Field(default=None)


class IdsInfo(_Strict):
    """Metadata for the IDS document."""
    title: str
    description: str | None = Field(default=None)
    copyright: str | None = Field(default=None)
    version: str | None = Field(default=None)
    author: str | None = Field(default=None, description="Email address")
    date: str | None = Field(default=None, description="ISO date YYYY-MM-DD")
    purpose: str | None = Field(default=None)
    milestone: str | None = Field(default=None)


class IdsDocument(_Strict):
    """Top-level IDS document — the root object the LLM must produce."""
    info: IdsInfo
    specifications: list[Specification] = Field(min_length=1)
