"""Hardcoded rule declarations for the current resource types."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias


@dataclass(frozen=True)
class RequiredRelationRuleSpec:
    kind: Literal["required_relation"] = field(init=False, default="required_relation")
    id: str
    label: str
    description: str
    resource_type: str
    relation: str
    min_count: int = 1
    max_count: int | None = None


@dataclass(frozen=True)
class RequiredFieldsRuleSpec:
    kind: Literal["required_fields"] = field(init=False, default="required_fields")
    id: str
    label: str
    description: str
    resource_type: str
    fields: tuple[str, ...] | None = None
    excluded_roots: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    each_repeatable_entry: bool = True


@dataclass(frozen=True)
class UniqueNumberRuleSpec:
    kind: Literal["unique_number"] = field(init=False, default="unique_number")
    id: str
    label: str
    description: str
    resource_type: str
    value_fields: tuple[str, ...]
    group_by: tuple[str, ...] = ()
    base_scope_only: bool = True
    number_pattern: str | None = None


@dataclass(frozen=True)
class ContinuousNumberRuleSpec:
    kind: Literal["continuous_number"] = field(init=False, default="continuous_number")
    id: str
    label: str
    description: str
    resource_type: str
    value_fields: tuple[str, ...]
    group_by: tuple[str, ...] = ()
    start_at: int | None = None
    base_scope_only: bool = True
    number_pattern: str | None = None


@dataclass(frozen=True)
class SpatialWithinRuleSpec:
    kind: Literal["spatial_within"] = field(init=False, default="spatial_within")
    id: str
    label: str
    description: str
    resource_type: str
    relation: str


RuleSpec: TypeAlias = (
    RequiredRelationRuleSpec
    | RequiredFieldsRuleSpec
    | UniqueNumberRuleSpec
    | ContinuousNumberRuleSpec
    | SpatialWithinRuleSpec
)


CONTEXT_RULE_SPECS: tuple[RuleSpec, ...] = (
    RequiredRelationRuleSpec(
        id="trench",
        label="Powiązanie z Trench",
        description="Context wskazuje jeden istniejący Trench.",
        resource_type="context",
        relation="trench",
        min_count=1,
        max_count=1,
    ),
    ContinuousNumberRuleSpec(
        id="number_continuity",
        label="Ciągłość numeracji",
        description="Brak luk między numerami Context w wybranym zakresie i trenchu.",
        resource_type="context",
        value_fields=("number",),
        group_by=("trench",),
        start_at=None,
    ),
    UniqueNumberRuleSpec(
        id="number_unique",
        label="Unikalny Context Number",
        description="Numer Context nie powtarza się w wybranym zakresie i trenchu.",
        resource_type="context",
        value_fields=("number",),
        group_by=("trench",),
    ),
    RequiredFieldsRuleSpec(
        id="complete",
        label="Kompletność pól",
        description="Wymagane pola i każdy wpis grupy powtarzalnej są wypełnione.",
        resource_type="context",
        fields=None,
        excluded_roots=(
            "harris_above",
            "harris_below",
            "harris_same_level",
            "photos_or_drawings",
            "spatial_extent",
            "descriptive_information",
        ),
        optional_fields=("comment",),
        each_repeatable_entry=True,
    ),
    RequiredRelationRuleSpec(
        id="linked_3d",
        label="Powiązanie z 3D",
        description="Istnieje zasób Digital Resource 3D wskazujący ten Context.",
        resource_type="context",
        relation="3d",
    ),
    RequiredRelationRuleSpec(
        id="linked_iiif",
        label="Powiązanie z IIIF",
        description="Istnieje zasób Digital Resource IIIF wskazujący ten Context.",
        resource_type="context",
        relation="iiif",
    ),
    RequiredRelationRuleSpec(
        id="linked_pottery",
        label="Powiązanie z Pottery Collection",
        description="Istnieje Pottery Collection wskazujący ten Context.",
        resource_type="context",
        relation="pottery",
    ),
)

SPECIAL_FIND_RULE_SPECS: tuple[RuleSpec, ...] = (
    RequiredRelationRuleSpec("context", "Powiązanie z Context", "Special Find wskazuje istniejący Context.", "special_find", "context", 1, 1),
    ContinuousNumberRuleSpec("number_continuity", "Ciągłość Special Find No", "Ciągłość numerów osobno dla Prefix.", "special_find", ("number",), ("prefix",)),
    ContinuousNumberRuleSpec("order_continuity", "Ciągłość Order Number", "Ciągłość numerów w ramach Category i Context.", "special_find", ("order_number",), ("category", "context"), number_pattern=r"[A-Za-z]*([0-9]+)"),
    UniqueNumberRuleSpec("number_unique", "Unikalny Special Find No", "Special Find No nie powtarza się w ramach Prefix.", "special_find", ("number",), ("prefix",)),
    UniqueNumberRuleSpec("order_unique", "Unikalny Order Number", "Order Number nie powtarza się w ramach Category i Context.", "special_find", ("order_number",), ("category", "context"), number_pattern=r"[A-Za-z]*([0-9]+)"),
    SpatialWithinRuleSpec("within_context", "Położenie w Context", "Punkt Special Find leży wewnątrz poligonu powiązanego Context.", "special_find", "context"),
    SpatialWithinRuleSpec("within_trench", "Położenie w Trench", "Punkt Special Find leży wewnątrz poligonu powiązanego Trench.", "special_find", "trench"),
)

MODEL_3D_RULE_SPECS: tuple[RuleSpec, ...] = (
    RequiredRelationRuleSpec("related", "Powiązanie z zasobem", "Digital Resource 3D wskazuje istniejący zasób.", "digital_3d", "related"),
    RequiredFieldsRuleSpec("geospatial", "Geospatial", "Pole Geospatial ma wartość; false też jest wypełnioną wartością.", "digital_3d", fields=("geospatial",)),
)

IIIF_RULE_SPECS: tuple[RuleSpec, ...] = (
    RequiredRelationRuleSpec("related", "Powiązanie z zasobem", "Digital Resource IIIF wskazuje istniejący zasób.", "digital_iiif", "related"),
)

ANNOTATION_RULE_SPECS: tuple[RuleSpec, ...] = (
    RequiredRelationRuleSpec("related", "Powiązanie z zasobem", "Annotation wskazuje istniejący zasób.", "annotation", "related"),
)

POTTERY_RULE_SPECS: tuple[RuleSpec, ...] = (
    RequiredRelationRuleSpec("context", "Powiązanie z Context", "Pottery Collection wskazuje istniejący Context.", "pottery_collection", "context", 1, 1),
    RequiredFieldsRuleSpec("category", "Kategoria ceramiki", "Pole Pottery Type jest wypełnione.", "pottery_collection", fields=("category",)),
)

_RESOURCE_RULES: dict[str, tuple[RuleSpec, ...]] = {
    "context": CONTEXT_RULE_SPECS,
    "special_find": SPECIAL_FIND_RULE_SPECS,
    "digital_3d": MODEL_3D_RULE_SPECS,
    "digital_iiif": IIIF_RULE_SPECS,
    "annotation": ANNOTATION_RULE_SPECS,
    "pottery_collection": POTTERY_RULE_SPECS,
    **{
        resource_type: (
            RequiredRelationRuleSpec("pottery_collection", "Powiązanie z Pottery Collection", "Pottery Record wskazuje istniejącą Pottery Collection.", resource_type, "pottery_collection", 1, 1),
        )
        for resource_type in (
            "pottery_amphorae", "pottery_kitchen_ware", "pottery_lamps",
            "pottery_plain_ware", "pottery_storage_vessels", "pottery_table_ware",
        )
    },
}

# The same graph-aware completeness factory is available for every resource type.
# Context already declares its explicit exclusions and optional Comment above.
RULE_SPECS_BY_RESOURCE_TYPE: Mapping[str, tuple[RuleSpec, ...]] = MappingProxyType({
    resource_type: specs if resource_type == "context" else specs + (
        RequiredFieldsRuleSpec(
            id="complete", label="Kompletność pól",
            description="Wszystkie pola grafu i każdy istniejący wpis grupy powtarzalnej są wypełnione.",
            resource_type=resource_type,
        ),
    )
    for resource_type, specs in _RESOURCE_RULES.items()
})


def verdict(status: str, *messages: str) -> dict:
    return {"status": status, "messages": [message for message in messages if message]}
