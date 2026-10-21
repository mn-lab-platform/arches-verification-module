"""Compile rule declarations into evaluators over normalized resource facts."""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import json
import re

from .profiles import ResourceProfile
from .repository import integer_number, localized
from .rules import (
    ContinuousNumberRuleSpec,
    RequiredFieldsRuleSpec,
    RequiredRelationRuleSpec,
    RuleSpec,
    SpatialWithinRuleSpec,
    UniqueNumberRuleSpec,
    verdict,
)
from .types import ResourceFact, ResourceSnapshot

Verdict = dict[str, object]


@dataclass(frozen=True)
class NumberGap:
    group: tuple[str, ...]
    start: int
    end: int


@dataclass
class CompiledRule:
    id: str
    evaluate: Callable[[ResourceFact], Verdict]
    gaps: list[NumberGap] = field(default_factory=list)


@dataclass
class EvaluationResult:
    results: dict[str, dict[str, Verdict]]
    gaps: dict[str, list[NumberGap]]


def _relation_rule(
    spec: RequiredRelationRuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> CompiledRule:
    if spec.relation not in profile.related_graphs:
        raise ValueError(f"Nieznana relacja: {spec.relation}")
    if spec.min_count < 0 or (spec.max_count is not None and spec.max_count < spec.min_count):
        raise ValueError(f"Niepoprawne granice liczby relacji: {spec.id}")

    def evaluate(fact: ResourceFact) -> Verdict:
        state = fact.relations[spec.relation]
        actual = len(state.target_ids)
        valid = len(state.valid_target_ids)
        if actual == valid and actual >= spec.min_count and (spec.max_count is None or actual <= spec.max_count):
            return verdict("pass")
        if actual == 0:
            return verdict("fail", f"Brak powiązania: {spec.label}")
        if valid < actual:
            return verdict("fail", f"Powiązanie wskazuje nieistniejący zasób: {spec.label}")
        return verdict("fail", f"Niepoprawna liczba powiązań ({actual}): {spec.label}")

    return CompiledRule(spec.id, evaluate)


def _spatial_within_rule(
    spec: SpatialWithinRuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> CompiledRule:
    if spec.relation not in profile.related_graphs or not {"self", spec.relation}.issubset(profile.spatial_nodes):
        raise ValueError(f"Brak konfiguracji geometrii dla reguły {spec.id}")

    def evaluate(fact: ResourceFact) -> Verdict:
        relation = fact.relations[spec.relation]
        if not relation.target_ids:
            return verdict("fail", f"Brak powiązania: {spec.relation}")
        if len(relation.valid_target_ids) < len(relation.target_ids):
            return verdict("fail", f"Powiązanie wskazuje nieistniejący zasób: {spec.relation}")
        matches = fact.spatial.get(spec.relation, [])
        if len(matches) != len(relation.valid_target_ids):
            return verdict("fail", f"Brak wyniku porównania geometrii: {spec.relation}")
        if any(not match.source_has_geometry for match in matches):
            return verdict("fail", f"Brak geometrii zasobu: {profile.label}")
        if any(not match.target_has_geometry for match in matches):
            return verdict("fail", f"Brak geometrii powiązanego {spec.relation}")
        if any(not match.within for match in matches):
            return verdict("fail", f"Zasób leży poza powiązanym {spec.relation}")
        return verdict("pass")

    return CompiledRule(spec.id, evaluate)


def _excluded_nodes(
    roots: Iterable[str], edges: list[tuple[str, str]],
) -> set[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for parent, child in edges:
        children[parent].append(child)
    excluded = set(roots)
    pending = list(excluded)
    while pending:
        for child in children[pending.pop()]:
            if child not in excluded:
                excluded.add(child)
                pending.append(child)
    return excluded


def _fields_rule(
    spec: RequiredFieldsRuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> CompiledRule:
    unknown_fields = set(spec.fields or ()) - profile.fields.keys()
    unknown_roots = set(spec.excluded_roots) - profile.completeness_excluded_roots.keys()
    unknown_optional = set(spec.optional_fields) - profile.completeness_optional_fields.keys()
    if unknown_fields or unknown_roots or unknown_optional:
        raise ValueError(f"Nieznane pola reguły {spec.id}: {sorted(unknown_fields | unknown_roots | unknown_optional)}")

    roots = (profile.completeness_excluded_roots[name] for name in spec.excluded_roots)
    excluded = _excluded_nodes(roots, snapshot.edges)
    excluded.update(profile.completeness_optional_fields[name] for name in spec.optional_fields)
    selected = None if spec.fields is None else {profile.fields[name] for name in spec.fields}
    by_group: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for node in snapshot.nodes.values():
        if node.datatype == "semantic" or node.node_id in excluded:
            continue
        if selected is not None and node.node_id not in selected:
            continue
        if not node.nodegroup_id:
            raise ValueError(f"Pole {node.node_id} nie ma nodegroup")
        by_group[node.nodegroup_id].append((node.node_id, localized(node.name)))

    def evaluate(fact: ResourceFact) -> Verdict:
        messages: list[str] = []
        for group_id, nodes in by_group.items():
            entries = fact.group_values.get(group_id, [])
            if not entries:
                messages.extend(f"Brak pola: {label}" for _, label in nodes)
                continue
            if spec.each_repeatable_entry:
                for index, entry in enumerate(entries, start=1):
                    suffix = f" (wpis {index})" if len(entries) > 1 else ""
                    messages.extend(
                        f"Brak pola: {label}{suffix}"
                        for node_id, label in nodes if not entry.get(node_id, False)
                    )
            elif not any(all(entry.get(node_id, False) for node_id, _ in nodes) for entry in entries):
                best = min(entries, key=lambda entry: sum(not entry.get(node_id, False) for node_id, _ in nodes))
                messages.extend(f"Brak pola: {label}" for node_id, label in nodes if not best.get(node_id, False))
        return verdict("fail", *messages) if messages else verdict("pass")

    return CompiledRule(spec.id, evaluate)


def _group_value(fact: ResourceFact, profile: ResourceProfile, alias: str) -> str | None:
    if alias in profile.related_graphs:
        state = fact.relations[alias]
        if len(state.target_ids) == len(state.valid_target_ids) == 1:
            return state.valid_target_ids[0]
        return None
    values = fact.fields.get(alias, [])
    if len(values) != 1:
        return None
    value = values[0]
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)



def _number_label(snapshot: ResourceSnapshot, profile: ResourceProfile, alias: str) -> str:
    return localized(snapshot.nodes[profile.fields[alias]].name) or alias


def _number_scope(
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    value_fields: tuple[str, ...],
    group_by: tuple[str, ...],
    cohort_ids: set[str],
    number_pattern: str | None = None,
) -> tuple[dict[str, tuple[tuple[str, ...], tuple[int, ...]]], dict[str, str]]:
    if not value_fields or set(value_fields) - profile.fields.keys():
        raise ValueError(f"Nieznane pola numeracji: {value_fields}")
    if set(group_by) - (profile.fields.keys() | profile.related_graphs.keys()):
        raise ValueError(f"Nieznane pola grupujące: {group_by}")
    keys = {}
    errors = {}
    for resource_id in cohort_ids:
        fact = snapshot.resources[resource_id]
        numbers = []
        for alias in value_fields:
            values = fact.fields.get(alias, [])
            if len(values) == 1 and number_pattern is not None:
                match = re.fullmatch(number_pattern, str(values[0]).strip())
                number = int(match.group(1)) if match else None
            else:
                number = integer_number(values[0]) if len(values) == 1 else None
            if number is None:
                errors[resource_id] = f"Brak jednego poprawnego, całkowitego {_number_label(snapshot, profile, alias)}"
                break
            numbers.append(number)
        else:
            group = tuple(_group_value(fact, profile, alias) for alias in group_by)
            if any(value is None for value in group):
                errors[resource_id] = f"Brak jednej poprawnej grupy numeracji: {', '.join(group_by)}"
                continue
            keys[resource_id] = (group, tuple(numbers))
    return keys, errors


def _number_rule_scope(
    spec: UniqueNumberRuleSpec | ContinuousNumberRuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> tuple[dict[str, tuple[tuple[str, ...], tuple[int, ...]]], dict[str, str]]:
    cohort_ids = base_ids if spec.base_scope_only else visible_ids
    return _number_scope(profile, snapshot, spec.value_fields, spec.group_by, cohort_ids, spec.number_pattern)


def _unique_rule(
    spec: UniqueNumberRuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> CompiledRule:
    keys, errors = _number_rule_scope(spec, profile, snapshot, base_ids, visible_ids)
    counts = Counter(keys.values())
    label = " / ".join(_number_label(snapshot, profile, alias) for alias in spec.value_fields)

    def evaluate(fact: ResourceFact) -> Verdict:
        if spec.base_scope_only and fact.resource_id not in base_ids:
            return verdict("not_applicable", "Dołączony spoza zakresu bazowego; numeracja dotyczy zakresu bazowego")
        if fact.resource_id in errors:
            return verdict("fail", errors[fact.resource_id])
        key = keys[fact.resource_id]
        count = counts[key]
        if count > 1:
            number = " / ".join(map(str, key[1]))
            return verdict("fail", f"{label} {number} występuje {count} razy w wybranym zakresie")
        return verdict("pass")

    return CompiledRule(spec.id, evaluate)


def _continuous_rule(
    spec: ContinuousNumberRuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> CompiledRule:
    if len(spec.value_fields) != 1:
        raise ValueError(f"Ciągłość wymaga jednego pola liczbowego: {spec.id}")
    keys, errors = _number_rule_scope(spec, profile, snapshot, base_ids, visible_ids)
    numbers_by_group: dict[tuple[str, ...], set[int]] = defaultdict(set)
    for group, numbers in keys.values():
        numbers_by_group[group].add(numbers[0])

    preceding: dict[tuple[tuple[str, ...], int], NumberGap] = {}
    gaps: list[NumberGap] = []
    for group, values in sorted(numbers_by_group.items()):
        numbers = sorted(values)
        previous = spec.start_at - 1 if spec.start_at is not None else numbers[0]
        for current in numbers:
            if current > previous + 1:
                gap = NumberGap(group, previous + 1, current - 1)
                preceding[(group, current)] = gap
                gaps.append(gap)
            previous = current
    label = _number_label(snapshot, profile, spec.value_fields[0])

    def evaluate(fact: ResourceFact) -> Verdict:
        if spec.base_scope_only and fact.resource_id not in base_ids:
            return verdict("not_applicable", "Dołączony spoza zakresu bazowego; numeracja dotyczy zakresu bazowego")
        if fact.resource_id in errors:
            return verdict("fail", errors[fact.resource_id])
        group, numbers = keys[fact.resource_id]
        gap = preceding.get((group, numbers[0]))
        if gap:
            missing = str(gap.start) if gap.start == gap.end else f"{gap.start}–{gap.end}"
            return verdict("fail", f"Brak numerów {missing} przed {label} {numbers[0]}")
        return verdict("pass")

    return CompiledRule(spec.id, evaluate, gaps)


RULE_FACTORIES = {
    RequiredRelationRuleSpec: _relation_rule,
    RequiredFieldsRuleSpec: _fields_rule,
    UniqueNumberRuleSpec: _unique_rule,
    ContinuousNumberRuleSpec: _continuous_rule,
    SpatialWithinRuleSpec: _spatial_within_rule,
}


def create_rule(
    spec: RuleSpec,
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> CompiledRule:
    """Build one evaluator from a hardcoded or future user-defined rule spec."""
    if spec.resource_type != profile.id or snapshot.resource_type != profile.id or snapshot.graph_id != profile.graph_id:
        raise ValueError(f"Reguła {spec.id} nie pasuje do profilu i danych")
    try:
        factory = RULE_FACTORIES[type(spec)]
    except KeyError:
        raise ValueError(f"Nieobsługiwany typ reguły: {type(spec).__name__}") from None
    return factory(spec, profile, snapshot, base_ids, visible_ids)


def evaluate_rules(
    specs: Iterable[RuleSpec],
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    base_ids: set[str],
    visible_ids: set[str],
) -> EvaluationResult:
    """Evaluate selected rules once per visible resource; cohort work is done once per rule."""
    if not base_ids <= visible_ids or not visible_ids <= snapshot.resources.keys():
        raise ValueError("Zakres zawiera nieznane zasoby")
    compiled = [create_rule(spec, profile, snapshot, base_ids, visible_ids) for spec in specs]
    if len({rule.id for rule in compiled}) != len(compiled):
        raise ValueError("Powtórzone ID reguły")
    return EvaluationResult(
        results={
            resource_id: {rule.id: rule.evaluate(snapshot.resources[resource_id]) for rule in compiled}
            for resource_id in visible_ids
        },
        gaps={rule.id: rule.gaps for rule in compiled if rule.gaps},
    )
