"""User-defined rule definitions mapped onto the existing rule specs.

A definition is JSON: {resource_type, kind, label, description, params}. Params refer to
IDs from /api/rule-builder-options (field node IDs, relation IDs such as "out:<node>"),
and those IDs become the spec aliases. RULE_KINDS describes the params for the frontend
form and drives validation, so both always agree. RuleStore keeps the rules in a JSON file
(VERIFY_RULES_PATH) together with each relation's resolved target graph.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Literal
import uuid

from .profiles import RelationProfile, ResourceProfile
from .rules import (
    RULE_SPECS_BY_RESOURCE_TYPE,
    ContinuousNumberRuleSpec,
    RequiredFieldsRuleSpec,
    RequiredRelationRuleSpec,
    RuleSpec,
    UniqueNumberRuleSpec,
)

MAX_LABEL_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 500
MAX_ID_LENGTH = 100
MAX_CHOICES = 50
MAX_PATTERN_LENGTH = 100
MAX_RULES_PER_RESOURCE_TYPE = 100
DEFINITION_KEYS = {"resource_type", "kind", "label", "description", "params"}
RULES_FILE_VERSION = 1


class RuleDefinitionError(ValueError):
    """The definition cannot become a rule; the message is shown to the user."""


class RuleNotFoundError(LookupError):
    """No stored custom rule has the requested ID."""


class RuleStoreError(RuntimeError):
    """The rules file cannot be read or written."""


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: Literal["choice", "choices", "integer", "boolean", "pattern"]
    options: str | None = None  # Key of the rule-builder-options list offered for this param.
    default: Any = None
    required: bool = False
    nullable: bool = False
    minimum: int | None = None
    min_items: int = 0


@dataclass(frozen=True)
class RuleKind:
    kind: str
    label: str
    description: str
    params: tuple[Param, ...]
    build: Callable[[str, str, str, str, dict[str, Any]], RuleSpec]
    dump: Callable[[Any], dict[str, Any]]


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_ID_LENGTH:
        raise RuleDefinitionError(f"Niepoprawna wartość: {label}")
    return value.strip()


def _param_value(param: Param, raw: Mapping[str, Any]) -> Any:
    if param.name not in raw:
        if param.required:
            raise RuleDefinitionError(f"Brak wartości: {param.label}")
        return param.default
    value = raw[param.name]
    if value is None or (param.type == "pattern" and value == ""):
        if not param.nullable:
            raise RuleDefinitionError(f"Brak wartości: {param.label}")
        return None

    if param.type == "choice":
        return _identifier(value, param.label)
    if param.type == "choices":
        if not isinstance(value, list):
            raise RuleDefinitionError(f"Oczekiwano listy: {param.label}")
        choices = tuple(dict.fromkeys(_identifier(item, param.label) for item in value))
        if len(choices) < param.min_items or len(choices) > MAX_CHOICES:
            raise RuleDefinitionError(f"Niepoprawna liczba wartości: {param.label}")
        return choices
    if param.type == "integer":
        # bool is an int subclass; JSON true must not pass as 1.
        if not isinstance(value, int) or isinstance(value, bool):
            raise RuleDefinitionError(f"Oczekiwano liczby całkowitej: {param.label}")
        if param.minimum is not None and value < param.minimum:
            raise RuleDefinitionError(f"Wartość poniżej {param.minimum}: {param.label}")
        return value
    if param.type == "boolean":
        if not isinstance(value, bool):
            raise RuleDefinitionError(f"Oczekiwano wartości tak/nie: {param.label}")
        return value
    if not isinstance(value, str) or len(value) > MAX_PATTERN_LENGTH:
        raise RuleDefinitionError(f"Niepoprawne wyrażenie: {param.label}")
    try:
        groups = re.compile(value).groups
    except re.error:
        raise RuleDefinitionError(f"Niepoprawne wyrażenie regularne: {param.label}") from None
    if groups < 1:
        raise RuleDefinitionError(f"Wyrażenie musi mieć grupę z numerem, np. [A-Z]*([0-9]+): {param.label}")
    return value


def _check_number_groups(value_fields: tuple[str, ...], group_by: tuple[str, ...]) -> None:
    if set(value_fields) & set(group_by):
        raise RuleDefinitionError("Pole numeracji nie może być jednocześnie polem grupującym")


def _build_relation(rule_id: str, label: str, description: str, resource_type: str, params: dict) -> RuleSpec:
    if params["max_count"] is not None and params["max_count"] < params["min_count"]:
        raise RuleDefinitionError("Maksymalna liczba powiązań jest mniejsza niż minimalna")
    return RequiredRelationRuleSpec(
        rule_id, label, description, resource_type,
        params["relation"], params["min_count"], params["max_count"],
    )


def _build_fields(rule_id: str, label: str, description: str, resource_type: str, params: dict) -> RuleSpec:
    return RequiredFieldsRuleSpec(
        rule_id, label, description, resource_type,
        fields=params["fields"],
        excluded_roots=params["excluded_fields"],
        optional_fields=params["optional_fields"],
        each_repeatable_entry=params["each_repeatable_entry"],
    )


def _build_unique(rule_id: str, label: str, description: str, resource_type: str, params: dict) -> RuleSpec:
    _check_number_groups(params["value_fields"], params["group_by"])
    return UniqueNumberRuleSpec(
        rule_id, label, description, resource_type,
        value_fields=params["value_fields"],
        group_by=params["group_by"],
        base_scope_only=params["base_scope_only"],
        number_pattern=params["number_pattern"],
    )


def _build_continuous(rule_id: str, label: str, description: str, resource_type: str, params: dict) -> RuleSpec:
    value_fields = (params["value_field"],)
    _check_number_groups(value_fields, params["group_by"])
    return ContinuousNumberRuleSpec(
        rule_id, label, description, resource_type,
        value_fields=value_fields,
        group_by=params["group_by"],
        start_at=params["start_at"],
        base_scope_only=params["base_scope_only"],
        number_pattern=params["number_pattern"],
    )


_GROUP_BY = Param("group_by", "Grupuj według", "choices", options="grouping", default=())
_BASE_SCOPE_ONLY = Param("base_scope_only", "Tylko zakres bazowy", "boolean", default=True)
_NUMBER_PATTERN = Param("number_pattern", "Wzorzec numeru", "pattern", default=None, nullable=True)

RULE_KINDS: Mapping[str, RuleKind] = MappingProxyType({kind.kind: kind for kind in (
    RuleKind(
        "required_relation", "Wymagane powiązanie",
        "Zasób ma określoną liczbę powiązań wskazujących istniejące zasoby.",
        (
            Param("relation", "Relacja", "choice", options="relations", required=True),
            Param("min_count", "Minimalna liczba", "integer", default=1, minimum=0),
            Param("max_count", "Maksymalna liczba", "integer", default=None, nullable=True, minimum=0),
        ),
        _build_relation,
        lambda spec: {"relation": spec.relation, "min_count": spec.min_count, "max_count": spec.max_count},
    ),
    RuleKind(
        "required_fields", "Kompletność pól",
        "Wybrane pola (lub wszystkie) są wypełnione, z pominięciem wykluczonych gałęzi.",
        (
            # null means every field of the graph.
            Param("fields", "Pola", "choices", options="fields", default=None, nullable=True, min_items=1),
            Param("excluded_fields", "Pomiń gałęzie", "choices", options="completeness_roots", default=()),
            Param("optional_fields", "Pola opcjonalne", "choices", options="fields", default=()),
            Param("each_repeatable_entry", "Każdy wpis grupy powtarzalnej", "boolean", default=True),
        ),
        _build_fields,
        lambda spec: {
            "fields": None if spec.fields is None else list(spec.fields),
            "excluded_fields": list(spec.excluded_roots),
            "optional_fields": list(spec.optional_fields),
            "each_repeatable_entry": spec.each_repeatable_entry,
        },
    ),
    RuleKind(
        "unique_number", "Unikalny numer",
        "Numer nie powtarza się w wybranym zakresie i grupie.",
        (
            Param("value_fields", "Pola numeru", "choices", options="numbering", required=True, min_items=1),
            _GROUP_BY, _BASE_SCOPE_ONLY, _NUMBER_PATTERN,
        ),
        _build_unique,
        lambda spec: {
            "value_fields": list(spec.value_fields),
            "group_by": list(spec.group_by),
            "base_scope_only": spec.base_scope_only,
            "number_pattern": spec.number_pattern,
        },
    ),
    RuleKind(
        "continuous_number", "Ciągła numeracja",
        "Brak luk w numeracji w wybranym zakresie i grupie.",
        (
            Param("value_field", "Pole numeru", "choice", options="numbering", required=True),
            _GROUP_BY,
            Param("start_at", "Numeracja od", "integer", default=None, nullable=True),
            _BASE_SCOPE_ONLY, _NUMBER_PATTERN,
        ),
        _build_continuous,
        lambda spec: {
            "value_field": spec.value_fields[0],
            "group_by": list(spec.group_by),
            "start_at": spec.start_at,
            "base_scope_only": spec.base_scope_only,
            "number_pattern": spec.number_pattern,
        },
    ),
)})


def parse_rule(data: Any, rule_id: str) -> RuleSpec:
    """Validate a definition's structure and build its spec; check_choices verifies graph IDs."""
    if not isinstance(data, Mapping):
        raise RuleDefinitionError("Definicja zasady musi być obiektem JSON")
    unknown = set(data) - DEFINITION_KEYS
    if unknown:
        raise RuleDefinitionError(f"Nieznane pola definicji: {', '.join(sorted(map(str, unknown)))}")
    resource_type = data.get("resource_type")
    if resource_type not in RULE_SPECS_BY_RESOURCE_TYPE:
        raise RuleDefinitionError("Nieznany typ zasobu")
    kind = RULE_KINDS.get(data.get("kind"))
    if kind is None:
        raise RuleDefinitionError("Nieznany rodzaj zasady")

    label = data.get("label")
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > MAX_LABEL_LENGTH:
        raise RuleDefinitionError(f"Nazwa zasady jest wymagana (do {MAX_LABEL_LENGTH} znaków)")
    description = data.get("description") or ""
    if not isinstance(description, str) or len(description.strip()) > MAX_DESCRIPTION_LENGTH:
        raise RuleDefinitionError(f"Opis może mieć do {MAX_DESCRIPTION_LENGTH} znaków")

    raw_params = data.get("params", {})
    if not isinstance(raw_params, Mapping):
        raise RuleDefinitionError("Parametry zasady muszą być obiektem JSON")
    unknown = set(raw_params) - {param.name for param in kind.params}
    if unknown:
        raise RuleDefinitionError(f"Nieznane parametry: {', '.join(sorted(map(str, unknown)))}")
    params = {param.name: _param_value(param, raw_params) for param in kind.params}
    return kind.build(rule_id, label.strip(), description.strip(), resource_type, params)


def rule_to_dict(spec: RuleSpec) -> dict[str, Any]:
    """Inverse of parse_rule, plus the rule ID."""
    kind = RULE_KINDS.get(spec.kind)
    if kind is None:
        raise RuleDefinitionError(f"Rodzaj zasady niedostępny dla zasad użytkownika: {spec.kind}")
    return {
        "id": spec.id,
        "resource_type": spec.resource_type,
        "kind": spec.kind,
        "label": spec.label,
        "description": spec.description,
        "params": kind.dump(spec),
    }


def _available_ids(options: Mapping[str, Any]) -> dict[str, set[str]]:
    """IDs offered by rule-builder-options, keyed like Param.options."""
    def node_ids(items: list[dict]) -> set[str]:
        return {item["node_id"] for item in items}

    return {
        "relations": {item["id"] for item in options["relations"]},
        "fields": node_ids(options["fields"]),
        "completeness_roots": node_ids(options["completeness_roots"]),
        "numbering": node_ids(options["numbering"]),
        "grouping": node_ids(options["grouping"]["fields"]) | {item["id"] for item in options["grouping"]["relations"]},
    }


def check_choices(spec: RuleSpec, options: Mapping[str, Any]) -> None:
    """Every ID in the rule must be offered by rule-builder-options of its resource type."""
    if options["model"]["resource_type"] != spec.resource_type:
        raise RuleDefinitionError("Opcje grafu nie pasują do typu zasobu zasady")
    params = rule_to_dict(spec)["params"]
    available = _available_ids(options)
    for param in RULE_KINDS[spec.kind].params:
        value = params[param.name]
        if param.options is None or value is None:
            continue
        missing = [item for item in (value if param.type == "choices" else [value])
                   if item not in available[param.options]]
        if missing:
            raise RuleDefinitionError(f"Niedostępne w grafie ({param.label}): {', '.join(missing)}")


def rule_kinds() -> list[dict[str, Any]]:
    """Form schema for the frontend: one entry per kind with its params."""
    return [
        {
            "kind": kind.kind,
            "label": kind.label,
            "description": kind.description,
            "params": [
                {**asdict(param), "default": list(param.default) if isinstance(param.default, tuple) else param.default}
                for param in kind.params
            ],
        }
        for kind in RULE_KINDS.values()
    ]


def _relation_ids(spec: RuleSpec) -> set[str]:
    """Builder relation IDs ("out:…", "in:…") used by the rule; fields are plain node UUIDs."""
    params = rule_to_dict(spec)["params"]
    relation_ids = set()
    for param in RULE_KINDS[spec.kind].params:
        value = params[param.name]
        if param.options not in ("relations", "grouping") or value is None:
            continue
        relation_ids.update(
            item for item in (value if param.type == "choices" else [value])
            if item.startswith(("out:", "in:"))
        )
    return relation_ids


def relation_bindings(spec: RuleSpec, options: Mapping[str, Any]) -> dict[str, RelationProfile]:
    """Resolve relation IDs once, so running the rule later needs no graph metadata."""
    by_id = {item["id"]: item for item in options["relations"]}
    bindings = {}
    for relation_id in sorted(_relation_ids(spec)):
        option = by_id[relation_id]
        if option["direction"] == "incoming":
            graph_id = option["source_graph_id"]
        else:
            # With several or no target graphs any existing resource is a valid target.
            targets = option["target_graphs"]
            graph_id = targets[0]["graph_id"] if len(targets) == 1 else None
        bindings[relation_id] = RelationProfile(graph_id, option["node_id"], option["direction"])
    return bindings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_rule_id() -> str:
    return f"custom_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class CustomRule:
    spec: RuleSpec
    relations: Mapping[str, RelationProfile]
    created_at: str
    updated_at: str

    def to_record(self) -> dict[str, Any]:
        return {
            **rule_to_dict(self.spec),
            "relations": {relation_id: asdict(relation) for relation_id, relation in self.relations.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CustomRule":
        spec = parse_rule({key: record[key] for key in DEFINITION_KEYS if key in record}, record["id"])
        relations = {relation_id: RelationProfile(**value) for relation_id, value in record["relations"].items()}
        if _relation_ids(spec) - relations.keys():
            raise RuleStoreError(f"Brak powiązań relacji dla zasady {spec.id}")
        return cls(spec, MappingProxyType(relations), record["created_at"], record["updated_at"])


def build_custom_rule(
    data: Any, options: Mapping[str, Any], rule_id: str, created_at: str | None = None,
) -> CustomRule:
    """Parse a submitted definition, check it against the graph and resolve its relations."""
    spec = parse_rule(data, rule_id)
    check_choices(spec, options)
    now = _now()
    return CustomRule(spec, MappingProxyType(relation_bindings(spec, options)), created_at or now, now)


def extend_profile(profile: ResourceProfile, rules: Iterable[CustomRule]) -> ResourceProfile:
    """Add the fields and relations used by custom rules, aliased by their builder IDs.

    The loader and the engine only see what the profile declares, so this is all they need.
    Builtin aliases are names and custom ones are UUIDs or "out:"/"in:" IDs, so they never clash.
    """
    rules = [rule for rule in rules if rule.spec.resource_type == profile.id]
    if not rules:
        return profile
    fields = dict(profile.fields)
    related_graphs = dict(profile.related_graphs)
    excluded_roots = dict(profile.completeness_excluded_roots)
    optional_fields = dict(profile.completeness_optional_fields)
    for rule in rules:
        spec = rule.spec
        related_graphs.update(rule.relations)
        if isinstance(spec, RequiredFieldsRuleSpec):
            fields.update((node_id, node_id) for node_id in spec.fields or ())
            excluded_roots.update((node_id, node_id) for node_id in spec.excluded_roots)
            optional_fields.update((node_id, node_id) for node_id in spec.optional_fields)
        elif isinstance(spec, (UniqueNumberRuleSpec, ContinuousNumberRuleSpec)):
            fields.update(
                (node_id, node_id) for node_id in (*spec.value_fields, *spec.group_by)
                if node_id not in rule.relations
            )
    return replace(
        profile,
        fields=MappingProxyType(fields),
        related_graphs=MappingProxyType(related_graphs),
        completeness_excluded_roots=MappingProxyType(excluded_roots),
        completeness_optional_fields=MappingProxyType(optional_fields),
    )


class RuleStore:
    """Custom rules in one JSON file, replaced atomically on every change.

    The lock only covers threads of one process, so run the service with a single worker.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> list[CustomRule]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            raise RuleStoreError(f"Nie można odczytać pliku zasad: {error}") from error
        if not isinstance(data, dict) or data.get("version") != RULES_FILE_VERSION or not isinstance(data.get("rules"), list):
            raise RuleStoreError("Nieobsługiwany format pliku zasad")
        try:
            return [CustomRule.from_record(record) for record in data["rules"]]
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise RuleStoreError(f"Uszkodzony plik zasad: {error}") from error

    def _write(self, rules: list[CustomRule]) -> None:
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(
                    {"version": RULES_FILE_VERSION, "rules": [rule.to_record() for rule in rules]},
                    file, ensure_ascii=False, indent=2,
                )
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise RuleStoreError(f"Nie można zapisać pliku zasad: {error}") from error

    @staticmethod
    def _index(rules: list[CustomRule], rule_id: str) -> int:
        index = next((index for index, rule in enumerate(rules) if rule.spec.id == rule_id), None)
        if index is None:
            raise RuleNotFoundError(rule_id)
        return index

    def rules(self, resource_type: str | None = None) -> list[CustomRule]:
        with self._lock:
            rules = self._read()
        return [rule for rule in rules if resource_type is None or rule.spec.resource_type == resource_type]

    def get(self, rule_id: str) -> CustomRule:
        rules = self.rules()
        return rules[self._index(rules, rule_id)]

    def add(self, rule: CustomRule) -> None:
        with self._lock:
            rules = self._read()
            if any(existing.spec.id == rule.spec.id for existing in rules):
                raise RuleDefinitionError("Zasada o tym ID już istnieje")
            if sum(existing.spec.resource_type == rule.spec.resource_type for existing in rules) >= MAX_RULES_PER_RESOURCE_TYPE:
                raise RuleDefinitionError(f"Osiągnięto limit {MAX_RULES_PER_RESOURCE_TYPE} zasad dla tego typu zasobu")
            self._write([*rules, rule])

    def replace(self, rule: CustomRule) -> None:
        with self._lock:
            rules = self._read()
            index = self._index(rules, rule.spec.id)
            if rules[index].spec.resource_type != rule.spec.resource_type:
                raise RuleDefinitionError("Nie można zmienić typu zasobu istniejącej zasady")
            rules[index] = rule
            self._write(rules)

    def delete(self, rule_id: str) -> None:
        with self._lock:
            rules = self._read()
            del rules[self._index(rules, rule_id)]
            self._write(rules)


@lru_cache(maxsize=1)
def rule_store() -> RuleStore:
    return RuleStore(os.environ.get("VERIFY_RULES_PATH", "/data/custom_rules.json"))
