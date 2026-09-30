"""Read Arches tables and reduce them to the facts needed by Context rules."""

import os
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import (
    COMPLETENESS_EXCLUDED_ROOTS,
    COMPLETENESS_OPTIONAL_NODES,
    CONTEXT_GRAPH_ID,
    CONTEXT_HARRIS_NODE_IDS,
    CONTEXT_NUMBER_NODE_ID,
    CONTEXT_TRENCH_NODE_ID,
    IIIF_CONTEXT_NODE_ID,
    IIIF_GRAPH_ID,
    MODEL_3D_CONTEXT_NODE_ID,
    MODEL_3D_GRAPH_ID,
    POTTERY_CONTEXT_NODE_ID,
    POTTERY_GRAPH_ID,
    TRENCH_GRAPH_ID,
)
from .types import ContextFact, Snapshot


class DataModelError(RuntimeError):
    """The database no longer has the graph shape expected by the rules."""


def localized(value: Any) -> str:
    if isinstance(value, dict):
        if "value" in value:
            return localized(value["value"])
        for key in ("pl", "pl-PL", "en", "en-US"):
            if key in value:
                result = localized(value[key])
                if result:
                    return result
        return next((localized(item) for item in value.values() if localized(item)), "")
    if isinstance(value, list):
        return next((localized(item) for item in value if localized(item)), "")
    return str(value or "").strip()


def resource_name(resource: dict[str, Any]) -> str:
    descriptors = resource.get("descriptors") or {}
    candidates = [descriptors.get("name")]
    for key in ("pl", "pl-PL", "en", "en-US"):
        nested = descriptors.get(key)
        if isinstance(nested, dict):
            candidates.append(nested.get("name"))
    candidates.append(resource.get("name"))
    return next((label for value in candidates if (label := localized(value))), resource["resourceinstanceid"])


def has_value(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        if "value" in value:
            return has_value(value["value"])
        if "resourceId" in value:
            return has_value(value["resourceId"])
        return any(has_value(item) for item in value.values())
    if isinstance(value, list):
        return any(has_value(item) for item in value)
    return True  # 0 and False are filled values.


def related_ids(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(related_ids(item) for item in value)) if value else set()
    if isinstance(value, dict):
        if value.get("resourceId"):
            return {str(value["resourceId"])}
        return related_ids(value.get("value"))
    return set()


def context_number(value: Any) -> int | None:
    if isinstance(value, bool) or not has_value(value):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return int(number) if number == number.to_integral_value() else None


def completeness_nodes(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id = {node["nodeid"]: node for node in nodes}
    expected = {
        CONTEXT_NUMBER_NODE_ID,
        CONTEXT_TRENCH_NODE_ID,
        *CONTEXT_HARRIS_NODE_IDS,
        *COMPLETENESS_EXCLUDED_ROOTS,
        *COMPLETENESS_OPTIONAL_NODES,
    }
    missing = expected - by_id.keys()
    if missing:
        raise DataModelError(f"Brak oczekiwanych pól grafu Context: {', '.join(sorted(missing))}")

    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        children[edge["domainnodeid"]].append(edge["rangenodeid"])
    excluded = set(COMPLETENESS_EXCLUDED_ROOTS)
    pending = list(excluded)
    while pending:
        for child in children[pending.pop()]:
            if child not in excluded:
                excluded.add(child)
                pending.append(child)
    excluded.update(COMPLETENESS_OPTIONAL_NODES)

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if node["datatype"] != "semantic" and node["nodeid"] not in excluded:
            group_id = node["nodegroupid"]
            if not group_id:
                raise DataModelError(f"Pole {node['nodeid']} nie ma nodegroup")
            by_group[group_id].append(node)
    return dict(by_group)


def build_snapshot(
    graphs: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    tiles: list[dict[str, Any]],
    generated_at: str | None = None,
) -> Snapshot:
    expected_graphs = {CONTEXT_GRAPH_ID, TRENCH_GRAPH_ID, MODEL_3D_GRAPH_ID, IIIF_GRAPH_ID, POTTERY_GRAPH_ID}
    available_graphs = {graph["graphid"] for graph in graphs if graph["is_active"]}
    if not expected_graphs <= available_graphs:
        raise DataModelError("Nie wszystkie wymagane grafy zasobów są aktywne")

    required_by_group = completeness_nodes(nodes, edges)
    by_resource = {row["resourceinstanceid"]: row for row in resources}
    context_ids = {row["resourceinstanceid"] for row in resources if row["graphid"] == CONTEXT_GRAPH_ID}
    trenches = {
        row["resourceinstanceid"]: resource_name(row)
        for row in resources if row["graphid"] == TRENCH_GRAPH_ID
    }
    context_tiles: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    inbound: dict[str, dict[str, set[str]]] = {
        "3d": defaultdict(set), "iiif": defaultdict(set), "pottery": defaultdict(set)
    }
    relation_nodes = {
        MODEL_3D_GRAPH_ID: (MODEL_3D_CONTEXT_NODE_ID, "3d"),
        IIIF_GRAPH_ID: (IIIF_CONTEXT_NODE_ID, "iiif"),
        POTTERY_GRAPH_ID: (POTTERY_CONTEXT_NODE_ID, "pottery"),
    }
    for tile in tiles:
        resource_id = tile["resourceinstanceid"]
        resource = by_resource.get(resource_id)
        if resource is None:
            continue
        data = tile.get("tiledata") or {}
        graph_id = resource["graphid"]
        if graph_id == CONTEXT_GRAPH_ID:
            context_tiles[resource_id][tile["nodegroupid"]].append(data)
        elif graph_id in relation_nodes:
            node_id, kind = relation_nodes[graph_id]
            for target_id in related_ids(data.get(node_id)) & context_ids:
                inbound[kind][target_id].add(resource_id)

    facts: dict[str, ContextFact] = {}
    for resource_id in context_ids:
        row = by_resource[resource_id]
        groups = context_tiles[resource_id]
        all_data = [data for group_tiles in groups.values() for data in group_tiles]
        raw_trench_ids = set().union(*(related_ids(data.get(CONTEXT_TRENCH_NODE_ID)) for data in all_data))
        valid_trench_ids = raw_trench_ids & trenches.keys()
        if len(raw_trench_ids) == len(valid_trench_ids) == 1:
            trench_id = next(iter(valid_trench_ids))
            trench_issue = None
        else:
            trench_id = None
            trench_issue = (
                "Brak powiązania z istniejącym Trench" if not raw_trench_ids or not valid_trench_ids
                else "Context ma niejednoznaczne lub nieistniejące powiązanie z Trench"
            )

        raw_numbers = [data[CONTEXT_NUMBER_NODE_ID] for data in all_data if has_value(data.get(CONTEXT_NUMBER_NODE_ID))]
        number = context_number(raw_numbers[0]) if len(raw_numbers) == 1 else None
        number_issue = None if number is not None else "Brak jednego poprawnego, całkowitego Context Number"
        harris_ids = sorted(
            set().union(*(related_ids(data.get(node_id)) for data in all_data for node_id in CONTEXT_HARRIS_NODE_IDS))
            & context_ids - {resource_id}
        )

        completeness_issues = []
        for group_id, group_nodes in required_by_group.items():
            group_tiles = groups.get(group_id, [])
            if not group_tiles:
                completeness_issues.extend(f"Brak pola: {localized(node['name'])}" for node in group_nodes)
                continue
            for index, data in enumerate(group_tiles, start=1):
                suffix = f" (wpis {index})" if len(group_tiles) > 1 else ""
                completeness_issues.extend(
                    f"Brak pola: {localized(node['name'])}{suffix}"
                    for node in group_nodes if not has_value(data.get(node["nodeid"]))
                )

        created = row["createdtime"]
        facts[resource_id] = ContextFact(
            resource_id=resource_id,
            name=resource_name(row),
            created_at=created.isoformat(timespec="seconds") if isinstance(created, datetime) else str(created),
            trench_id=trench_id,
            trench_issue=trench_issue,
            number=number,
            number_issue=number_issue,
            harris_ids=harris_ids,
            completeness_issues=completeness_issues,
            has_3d=bool(inbound["3d"].get(resource_id)),
            has_iiif=bool(inbound["iiif"].get(resource_id)),
            has_pottery=bool(inbound["pottery"].get(resource_id)),
        )
    return Snapshot(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        trenches=trenches,
        contexts=facts,
    )


def load_snapshot() -> Snapshot:
    """Read every needed table from the same PostgreSQL snapshot."""
    import psycopg
    from psycopg.rows import dict_row

    config = {
        "host": os.environ["VERIFY_DB_HOST"],
        "port": int(os.environ.get("VERIFY_DB_PORT", "5432")),
        "dbname": os.environ["VERIFY_DB_NAME"],
        "user": os.environ["VERIFY_DB_USER"],
        "password": os.environ["VERIFY_DB_PASSWORD"],
        "connect_timeout": 5,
        "row_factory": dict_row,
    }
    ids = (CONTEXT_GRAPH_ID, TRENCH_GRAPH_ID, MODEL_3D_GRAPH_ID, IIIF_GRAPH_ID, POTTERY_GRAPH_ID)
    with psycopg.connect(**config) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '120s'")
            graphs = connection.execute(
                "SELECT graphid::text, is_active FROM graphs WHERE graphid IN (%s,%s,%s,%s,%s)", ids
            ).fetchall()
            nodes = connection.execute(
                "SELECT nodeid::text, nodegroupid::text, datatype, name FROM nodes WHERE graphid = %s",
                (CONTEXT_GRAPH_ID,),
            ).fetchall()
            edges = connection.execute(
                "SELECT domainnodeid::text, rangenodeid::text FROM edges WHERE graphid = %s",
                (CONTEXT_GRAPH_ID,),
            ).fetchall()
            resources = connection.execute(
                "SELECT resourceinstanceid::text, graphid::text, createdtime, descriptors, name "
                "FROM resource_instances WHERE graphid IN (%s,%s,%s,%s,%s)", ids
            ).fetchall()
            tiles = connection.execute(
                "SELECT resourceinstanceid::text, nodegroupid::text, tiledata FROM tiles "
                "WHERE resourceinstanceid IN (SELECT resourceinstanceid FROM resource_instances "
                "WHERE graphid IN (%s,%s,%s,%s)) ORDER BY sortorder, tileid",
                (CONTEXT_GRAPH_ID, MODEL_3D_GRAPH_ID, IIIF_GRAPH_ID, POTTERY_GRAPH_ID),
            ).fetchall()
    return build_snapshot(graphs, nodes, edges, resources, tiles)
