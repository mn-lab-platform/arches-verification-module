"""Filter a cached snapshot, evaluate cohort rules and return ready-to-render rows."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from zoneinfo import ZoneInfo
from datetime import date, datetime, timezone

from .constants import CONTEXT_GRAPH_ID
from .rules import RULE_BY_ID, static_results, verdict
from .types import ContextFact, Snapshot


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


def _created_date(created_at: str) -> date:
    timestamp = datetime.fromisoformat(created_at)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(WARSAW).date()


def _format_gap(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}–{end}"


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


def build_report(snapshot: Snapshot, query: ReportQuery) -> dict:
    base_ids = {
        fact.resource_id for fact in snapshot.contexts.values()
        if (query.created_from is None or _created_date(fact.created_at) >= query.created_from)
        and (query.created_to is None or _created_date(fact.created_at) <= query.created_to)
        and (query.trench_id is None or fact.trench_id == query.trench_id)
    }
    visible_ids = set(base_ids)
    if query.include_harris:
        neighbors: dict[str, set[str]] = defaultdict(set)
        for fact in snapshot.contexts.values():
            for target in fact.harris_ids:
                if target in snapshot.contexts:
                    neighbors[fact.resource_id].add(target)
                    neighbors[target].add(fact.resource_id)
        for resource_id in base_ids:
            visible_ids.update(neighbors[resource_id])

    number_counts: dict[str, Counter] = defaultdict(Counter)
    for resource_id in base_ids:
        fact = snapshot.contexts[resource_id]
        if fact.trench_id and fact.number is not None:
            number_counts[fact.trench_id][fact.number] += 1

    preceding_gaps: dict[tuple[str, int], tuple[int, int]] = {}
    gaps = []
    if "number_continuity" in query.rule_ids:
        for trench_id, counts in sorted(number_counts.items(), key=lambda item: snapshot.trenches.get(item[0], "")):
            numbers = sorted(counts)
            missing_ranges = []
            for previous, current in zip(numbers, numbers[1:]):
                if current > previous + 1:
                    preceding_gaps[(trench_id, current)] = (previous + 1, current - 1)
                    missing_ranges.append({"from": previous + 1, "to": current - 1})
            if missing_ranges:
                gaps.append({
                    "trench_id": trench_id,
                    "trench_name": snapshot.trenches.get(trench_id, trench_id),
                    "ranges": missing_ranges,
                    "missing_count": sum(item["to"] - item["from"] + 1 for item in missing_ranges),
                })

    rows = []
    for resource_id in visible_ids:
        fact: ContextFact = snapshot.contexts[resource_id]
        results = static_results(fact)
        if resource_id not in base_ids:
            results["number_continuity"] = verdict("not_applicable", "Dołączony przez Harris; numeracja dotyczy zakresu bazowego")
            results["number_unique"] = verdict("not_applicable", "Dołączony przez Harris; numeracja dotyczy zakresu bazowego")
        elif fact.trench_id is None or fact.number is None:
            message = fact.number_issue or fact.trench_issue or "Nie można ocenić numeracji"
            results["number_continuity"] = verdict("fail", message)
            results["number_unique"] = verdict("fail", message)
        else:
            gap = preceding_gaps.get((fact.trench_id, fact.number))
            results["number_continuity"] = (
                verdict("fail", f"Brak numerów {_format_gap(*gap)} przed Context Number {fact.number}")
                if gap else verdict("pass")
            )
            count = number_counts[fact.trench_id][fact.number]
            results["number_unique"] = (
                verdict("fail", f"Context Number {fact.number} występuje {count} razy w wybranym zakresie")
                if count > 1 else verdict("pass")
            )

        selected = {rule_id: results[rule_id] for rule_id in query.rule_ids}
        failure_count = sum(result["status"] == "fail" for result in selected.values())
        overall_status = "fail" if failure_count else (
            "not_applicable" if all(result["status"] == "not_applicable" for result in selected.values()) else "pass"
        )
        rows.append({
            "resource_id": resource_id,
            "name": fact.name,
            "resource_url": f"/report/{resource_id}",
            "created_at": fact.created_at,
            "trench_id": fact.trench_id,
            "trench_name": snapshot.trenches.get(fact.trench_id or "", "—"),
            "number": fact.number,
            "source": "period" if resource_id in base_ids else "harris",
            "overall_status": overall_status,
            "failure_count": failure_count,
            "results": selected,
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
        "model": {"graph_id": CONTEXT_GRAPH_ID, "name": "(O) Context"},
        "generated_at": snapshot.generated_at,
        "timezone": "Europe/Warsaw",
        "rules": [{"id": rule_id, "label": RULE_BY_ID[rule_id].label} for rule_id in query.rule_ids],
        "summary": {
            "base_count": len(base_ids),
            "total_scope": total_scope,
            "passed": passed_count,
            "failed": failed_count,
            "not_applicable": total_scope - passed_count - failed_count,
        },
        "gaps": gaps,
        "page": query.page,
        "page_size": query.page_size,
        "pages": (total + query.page_size - 1) // query.page_size,
        "total": total,
        "rows": rows[offset:offset + query.page_size],
    }
