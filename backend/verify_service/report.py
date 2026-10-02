"""Filter a normalized snapshot and render verdicts from compiled rule specs."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .profiles import ResourceProfile
from .repository import integer_number
from .rule_engine import EvaluationResult, evaluate_rules
from .rules import RuleSpec
from .types import ResourceFact, ResourceSnapshot


@dataclass(frozen=True)
class ReportQuery:
    created_from: date | None
    created_to: date | None
    trench_id: str | None
    include_harris: bool
    rule_ids: tuple[str, ...]
    only_failed: bool = False
    sort: str = "created_desc"
    page: int = 1
    page_size: int = 100


SORTS = {
    "created_desc": "Najnowsze",
    "created_asc": "Najstarsze",
    "name_asc": "Nazwa A–Z",
    "name_desc": "Nazwa Z–A",
    "number_asc": "Numer rosnąco",
    "number_desc": "Numer malejąco",
    "failures_desc": "Najwięcej błędów",
}

WARSAW = ZoneInfo("Europe/Warsaw")
HARRIS_RELATIONS = ("harris_above", "harris_below", "harris_same_level")


def _created_date(created_at: str) -> date:
    timestamp = datetime.fromisoformat(created_at)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(WARSAW).date()


def _trench_id(fact: ResourceFact) -> str | None:
    relation = fact.relations.get("trench")
    if relation and len(relation.target_ids) == len(relation.valid_target_ids) == 1:
        return relation.valid_target_ids[0]
    return None


def _display_number(fact: ResourceFact) -> int | None:
    values = fact.fields.get("number", [])
    return integer_number(values[0]) if len(values) == 1 else None


def _sort_rows(rows: list[dict], sort: str) -> None:
    if sort == "created_asc":
        rows.sort(key=lambda row: (row["created_at"], row["resource_id"]))
    elif sort == "name_asc":
        rows.sort(key=lambda row: (row["name"].casefold(), row["resource_id"]))
    elif sort == "name_desc":
        rows.sort(key=lambda row: (row["name"].casefold(), row["resource_id"]), reverse=True)
    elif sort == "number_asc":
        rows.sort(key=lambda row: (row["number"] is None, row["number"] or 0, row["name"].casefold()))
    elif sort == "number_desc":
        rows.sort(key=lambda row: (row["number"] is None, -(row["number"] or 0), row["name"].casefold()))
    elif sort == "failures_desc":
        rows.sort(key=lambda row: (-row["failure_count"], row["name"].casefold()))
    else:
        rows.sort(key=lambda row: (row["created_at"], row["resource_id"]), reverse=True)


def _gap_rows(evaluation: EvaluationResult, snapshot: ResourceSnapshot) -> list[dict]:
    by_group: dict[tuple[str, tuple[str, ...]], list[dict[str, int]]] = defaultdict(list)
    for rule_id, gaps in evaluation.gaps.items():
        for gap in gaps:
            by_group[(rule_id, gap.group)].append({"from": gap.start, "to": gap.end})
    trenches = snapshot.related_resources.get("trench", {})
    rows = []
    for (rule_id, group), ranges in by_group.items():
        trench_id = group[0] if len(group) == 1 else None
        group_name = trenches.get(trench_id, trench_id) if trench_id else " / ".join(group)
        rows.append({
            "rule_id": rule_id,
            "group": list(group),
            "trench_id": trench_id,
            "trench_name": group_name,
            "ranges": ranges,
            "missing_count": sum(item["to"] - item["from"] + 1 for item in ranges),
        })
    rows.sort(key=lambda row: (row["trench_name"].casefold(), row["rule_id"]))
    return rows


def build_report(
    snapshot: ResourceSnapshot,
    profile: ResourceProfile,
    specs: tuple[RuleSpec, ...],
    query: ReportQuery,
) -> dict:
    """Select a cohort, run its chosen rules and return ready-to-render rows."""
    trenches = snapshot.related_resources.get("trench", {})
    base_ids = {
        fact.resource_id for fact in snapshot.resources.values()
        if (query.created_from is None or _created_date(fact.created_at) >= query.created_from)
        and (query.created_to is None or _created_date(fact.created_at) <= query.created_to)
        and (query.trench_id is None or _trench_id(fact) == query.trench_id)
    }
    visible_ids = set(base_ids)
    if query.include_harris:
        neighbors: dict[str, set[str]] = defaultdict(set)
        for fact in snapshot.resources.values():
            for alias in HARRIS_RELATIONS:
                relation = fact.relations.get(alias)
                if relation:
                    for target in relation.valid_target_ids:
                        if target in snapshot.resources:
                            neighbors[fact.resource_id].add(target)
                            neighbors[target].add(fact.resource_id)
        for resource_id in base_ids:
            visible_ids.update(neighbors[resource_id])

    by_id = {spec.id: spec for spec in specs}
    selected_specs = tuple(by_id[rule_id] for rule_id in query.rule_ids)
    evaluation = evaluate_rules(selected_specs, profile, snapshot, base_ids, visible_ids)

    rows = []
    for resource_id in visible_ids:
        fact = snapshot.resources[resource_id]
        results = evaluation.results[resource_id]
        failure_count = sum(result["status"] == "fail" for result in results.values())
        overall_status = "fail" if failure_count else (
            "not_applicable" if all(result["status"] == "not_applicable" for result in results.values()) else "pass"
        )
        trench_id = _trench_id(fact)
        rows.append({
            "resource_id": resource_id,
            "name": fact.name,
            "resource_url": f"/report/{resource_id}",
            "created_at": fact.created_at,
            "trench_id": trench_id,
            "trench_name": trenches.get(trench_id or "", "—"),
            "number": _display_number(fact),
            "source": "period" if resource_id in base_ids else "harris",
            "overall_status": overall_status,
            "failure_count": failure_count,
            "results": results,
        })

    failed_count = sum(row["overall_status"] == "fail" for row in rows)
    passed_count = sum(row["overall_status"] == "pass" for row in rows)
    total_scope = len(rows)
    if query.only_failed:
        rows = [row for row in rows if row["overall_status"] == "fail"]
    _sort_rows(rows, query.sort)
    total = len(rows)
    offset = (query.page - 1) * query.page_size
    return {
        "model": {"resource_type": profile.id, "graph_id": profile.graph_id, "name": profile.label},
        "generated_at": snapshot.generated_at,
        "timezone": "Europe/Warsaw",
        "rules": [{"id": spec.id, "label": spec.label} for spec in selected_specs],
        "summary": {
            "base_count": len(base_ids),
            "total_scope": total_scope,
            "passed": passed_count,
            "failed": failed_count,
            "not_applicable": total_scope - passed_count - failed_count,
        },
        "gaps": _gap_rows(evaluation, snapshot),
        "page": query.page,
        "page_size": query.page_size,
        "pages": (total + query.page_size - 1) // query.page_size,
        "total": total,
        "rows": rows[offset:offset + query.page_size],
    }
