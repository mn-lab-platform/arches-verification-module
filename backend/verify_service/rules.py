"""Hardcoded rule declarations and the current Context evaluators."""

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from .types import ContextFact


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    description: str


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

RULES = tuple(Rule(spec.id, spec.label, spec.description) for spec in CONTEXT_RULE_SPECS)
RULE_BY_ID = {rule.id: rule for rule in RULES}
ALL_RULE_IDS = tuple(rule.id for rule in RULES)


def verdict(status: str, *messages: str) -> dict:
    return {"status": status, "messages": [message for message in messages if message]}


def static_results(fact: ContextFact) -> dict[str, dict]:
    return {
        "trench": verdict("fail", fact.trench_issue) if fact.trench_issue else verdict("pass"),
        "complete": verdict("fail", *fact.completeness_issues) if fact.completeness_issues else verdict("pass"),
        "linked_3d": verdict("pass") if fact.has_3d else verdict("fail", "Brak powiązanego zasobu 3D"),
        "linked_iiif": verdict("pass") if fact.has_iiif else verdict("fail", "Brak powiązanego zasobu IIIF"),
        "linked_pottery": verdict("pass") if fact.has_pottery else verdict("fail", "Brak powiązanego Pottery Collection"),
    }
