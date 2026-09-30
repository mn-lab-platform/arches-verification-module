"""Public rule catalog and per-resource checks independent of date scope."""

from dataclasses import dataclass

from .types import ContextFact


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    description: str


RULES = (
    Rule("trench", "Powiązanie z Trench", "Context wskazuje jeden istniejący Trench."),
    Rule("number_continuity", "Ciągłość numeracji", "Brak luk między numerami Context w wybranym zakresie i trenchu."),
    Rule("number_unique", "Unikalny Context Number", "Numer Context nie powtarza się w wybranym zakresie i trenchu."),
    Rule("complete", "Kompletność pól", "Wymagane pola i każdy wpis grupy powtarzalnej są wypełnione."),
    Rule("linked_3d", "Powiązanie z 3D", "Istnieje zasób Digital Resource 3D wskazujący ten Context."),
    Rule("linked_iiif", "Powiązanie z IIIF", "Istnieje zasób Digital Resource IIIF wskazujący ten Context."),
    Rule("linked_pottery", "Powiązanie z Pottery Collection", "Istnieje Pottery Collection wskazujący ten Context."),
)
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
