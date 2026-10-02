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


RuleSpec: TypeAlias = (
    RequiredRelationRuleSpec
    | RequiredFieldsRuleSpec
    | UniqueNumberRuleSpec
    | ContinuousNumberRuleSpec
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

RULE_SPECS_BY_RESOURCE_TYPE: Mapping[str, tuple[RuleSpec, ...]] = MappingProxyType({
    "context": CONTEXT_RULE_SPECS,
})


def verdict(status: str, *messages: str) -> dict:
    return {"status": status, "messages": [message for message in messages if message]}
