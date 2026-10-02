"""Read Arches tables and normalize them according to a resource profile."""

import os
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .profiles import CONTEXT_PROFILE, ResourceProfile
from .types import ContextFact, NodeDefinition, RelationState, ResourceFact, ResourceSnapshot, Snapshot


class DataModelError(RuntimeError):
    """The database no longer has the graph shape expected by the profile."""


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


def integer_number(value: Any) -> int | None:
    if isinstance(value, bool) or not has_value(value):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return int(number) if number == number.to_integral_value() else None


# Keep the previous helper name available to existing callers.
context_number = integer_number


def completeness_nodes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    profile: ResourceProfile = CONTEXT_PROFILE,
) -> dict[str, list[dict[str, Any]]]:
    by_id = {node["nodeid"]: node for node in nodes}
    expected = {
        *profile.fields.values(),
        *profile.completeness_excluded_roots.values(),
        *profile.completeness_optional_fields.values(),
        *(relation.node_id for relation in profile.related_graphs.values() if relation.direction == "outgoing"),
    }
    missing = expected - by_id.keys()
    if missing:
        raise DataModelError(f"Brak oczekiwanych pól grafu {profile.label}: {', '.join(sorted(missing))}")

    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        children[edge["domainnodeid"]].append(edge["rangenodeid"])
    excluded = set(profile.completeness_excluded_roots.values())
    pending = list(excluded)
    while pending:
        for child in children[pending.pop()]:
            if child not in excluded:
                excluded.add(child)
                pending.append(child)
    excluded.update(profile.completeness_optional_fields.values())

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if node["datatype"] != "semantic" and node["nodeid"] not in excluded:
            group_id = node["nodegroupid"]
            if not group_id:
                raise DataModelError(f"Pole {node['nodeid']} nie ma nodegroup")
            by_group[group_id].append(node)
    return dict(by_group)


def _created_at(value: Any) -> str:
    return value.isoformat(timespec="seconds") if isinstance(value, datetime) else str(value)


def build_resource_snapshot(
    profile: ResourceProfile,
    graphs: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    tiles: list[dict[str, Any]],
    generated_at: str | None = None,
) -> ResourceSnapshot:
    """Reduce Arches rows to logical fields, relations and filled-field states."""
    expected_graphs = {profile.graph_id, *(relation.graph_id for relation in profile.related_graphs.values())}
    available_graphs = {graph["graphid"] for graph in graphs if graph["is_active"]}
    missing_graphs = expected_graphs - available_graphs
    if missing_graphs:
        raise DataModelError(f"Nieaktywne lub brakujące grafy: {', '.join(sorted(missing_graphs))}")

    node_definitions = {
        node["nodeid"]: NodeDefinition(
            node_id=node["nodeid"],
            nodegroup_id=node["nodegroupid"],
            datatype=node["datatype"],
            name=node["name"],
        )
        for node in nodes
    }
    expected_nodes = {
        *profile.fields.values(),
        *profile.completeness_excluded_roots.values(),
        *profile.completeness_optional_fields.values(),
        *(relation.node_id for relation in profile.related_graphs.values() if relation.direction == "outgoing"),
    }
    missing_nodes = expected_nodes - node_definitions.keys()
    if missing_nodes:
        raise DataModelError(f"Brak oczekiwanych pól grafu {profile.label}: {', '.join(sorted(missing_nodes))}")

    resources_by_graph: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    by_resource: dict[str, dict[str, Any]] = {}
    for row in resources:
        resource_id = row["resourceinstanceid"]
        resources_by_graph[row["graphid"]][resource_id] = row
        by_resource[resource_id] = row

    main_rows = resources_by_graph.get(profile.graph_id, {})
    main_ids = set(main_rows)
    field_nodes: dict[str, list[str]] = defaultdict(list)
    for logical_name, node_id in profile.fields.items():
        field_nodes[node_id].append(logical_name)
    outgoing_nodes: dict[str, list[str]] = defaultdict(list)
    incoming_by_graph: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for relation_name, relation in profile.related_graphs.items():
        if relation.direction == "outgoing":
            outgoing_nodes[relation.node_id].append(relation_name)
        else:
            incoming_by_graph[relation.graph_id].append((relation_name, relation.node_id))

    working: dict[str, dict[str, Any]] = {
        resource_id: {
            "fields": defaultdict(list),
            "relations": {
                name: {"target_ids": set(), "valid_target_ids": set()}
                for name in profile.related_graphs
            },
            "group_values": defaultdict(list),
        }
        for resource_id in main_ids
    }

    for tile in tiles:
        resource_id = tile["resourceinstanceid"]
        resource = by_resource.get(resource_id)
        if resource is None:
            continue
        graph_id = resource["graphid"]
        data = tile.get("tiledata") or {}
        if graph_id == profile.graph_id:
            current = working[resource_id]
            current["group_values"][tile["nodegroupid"]].append(
                {node_id: has_value(value) for node_id, value in data.items()}
            )
            for node_id, value in data.items():
                if has_value(value):
                    for logical_name in field_nodes.get(node_id, ()):
                        current["fields"][logical_name].append(value)
                relation_names = outgoing_nodes.get(node_id, ())
                if not relation_names:
                    continue
                targets = related_ids(value)
                for relation_name in relation_names:
                    relation = profile.related_graphs[relation_name]
                    current_relation = current["relations"][relation_name]
                    current_relation["target_ids"].update(targets)
                    current_relation["valid_target_ids"].update(
                        targets & resources_by_graph.get(relation.graph_id, {}).keys()
                    )
            continue

        for relation_name, node_id in incoming_by_graph.get(graph_id, []):
            for target_id in related_ids(data.get(node_id)) & main_ids:
                current_relation = working[target_id]["relations"][relation_name]
                current_relation["target_ids"].add(resource_id)
                current_relation["valid_target_ids"].add(resource_id)

    normalized_resources = {}
    for resource_id, row in main_rows.items():
        current = working[resource_id]
        normalized_resources[resource_id] = ResourceFact(
            resource_id=resource_id,
            name=resource_name(row),
            created_at=_created_at(row["createdtime"]),
            fields={name: values for name, values in current["fields"].items()},
            relations={
                name: RelationState(
                    target_ids=sorted(state["target_ids"]),
                    valid_target_ids=sorted(state["valid_target_ids"]),
                )
                for name, state in current["relations"].items()
            },
            group_values={group_id: values for group_id, values in current["group_values"].items()},
        )

    related_resources = {
        name: {
            resource_id: resource_name(row)
            for resource_id, row in resources_by_graph.get(relation.graph_id, {}).items()
        }
        for name, relation in profile.related_graphs.items()
    }
    return ResourceSnapshot(
        resource_type=profile.id,
        graph_id=profile.graph_id,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        nodes=node_definitions,
        edges=[(edge["domainnodeid"], edge["rangenodeid"]) for edge in edges],
        related_resources=related_resources,
        resources=normalized_resources,
    )


def _context_snapshot(
    normalized: ResourceSnapshot,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> Snapshot:
    """Keep the current API working until generic rule evaluators replace ContextFact."""
    required_by_group = completeness_nodes(nodes, edges, CONTEXT_PROFILE)
    facts: dict[str, ContextFact] = {}
    for resource_id, resource in normalized.resources.items():
        trench = resource.relations["trench"]
        raw_trench_ids = set(trench.target_ids)
        valid_trench_ids = set(trench.valid_target_ids)
        if len(raw_trench_ids) == len(valid_trench_ids) == 1:
            trench_id = next(iter(valid_trench_ids))
            trench_issue = None
        else:
            trench_id = None
            trench_issue = (
                "Brak powiązania z istniejącym Trench" if not raw_trench_ids or not valid_trench_ids
                else "Context ma niejednoznaczne lub nieistniejące powiązanie z Trench"
            )

        raw_numbers = resource.fields.get("number", [])
        number = integer_number(raw_numbers[0]) if len(raw_numbers) == 1 else None
        number_issue = None if number is not None else "Brak jednego poprawnego, całkowitego Context Number"
        harris_ids = sorted(
            set().union(*(
                resource.relations[name].valid_target_ids
                for name in ("harris_above", "harris_below", "harris_same_level")
            )) - {resource_id}
        )

        completeness_issues = []
        for group_id, group_nodes in required_by_group.items():
            group_entries = resource.group_values.get(group_id, [])
            if not group_entries:
                completeness_issues.extend(f"Brak pola: {localized(node['name'])}" for node in group_nodes)
                continue
            for index, values in enumerate(group_entries, start=1):
                suffix = f" (wpis {index})" if len(group_entries) > 1 else ""
                completeness_issues.extend(
                    f"Brak pola: {localized(node['name'])}{suffix}"
                    for node in group_nodes if not values.get(node["nodeid"], False)
                )

        facts[resource_id] = ContextFact(
            resource_id=resource_id,
            name=resource.name,
            created_at=resource.created_at,
            trench_id=trench_id,
            trench_issue=trench_issue,
            number=number,
            number_issue=number_issue,
            harris_ids=harris_ids,
            completeness_issues=completeness_issues,
            has_3d=bool(resource.relations["3d"].valid_target_ids),
            has_iiif=bool(resource.relations["iiif"].valid_target_ids),
            has_pottery=bool(resource.relations["pottery"].valid_target_ids),
        )
    return Snapshot(
        generated_at=normalized.generated_at,
        trenches=normalized.related_resources["trench"],
        contexts=facts,
    )


def build_snapshot(
    graphs: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    tiles: list[dict[str, Any]],
    generated_at: str | None = None,
) -> Snapshot:
    normalized = build_resource_snapshot(
        CONTEXT_PROFILE, graphs, nodes, edges, resources, tiles, generated_at
    )
    return _context_snapshot(normalized, nodes, edges)


def _database_config() -> dict[str, Any]:
    from psycopg.rows import dict_row

    return {
        "host": os.environ["VERIFY_DB_HOST"],
        "port": int(os.environ.get("VERIFY_DB_PORT", "5432")),
        "dbname": os.environ["VERIFY_DB_NAME"],
        "user": os.environ["VERIFY_DB_USER"],
        "password": os.environ["VERIFY_DB_PASSWORD"],
        "connect_timeout": 5,
        "row_factory": dict_row,
    }


def load_resource_snapshot(profile: ResourceProfile) -> ResourceSnapshot:
    """Read one profiled resource type from a consistent PostgreSQL snapshot."""
    import psycopg

    graph_ids = tuple(dict.fromkeys([
        profile.graph_id,
        *(relation.graph_id for relation in profile.related_graphs.values()),
    ]))
    placeholders = ",".join(["%s"] * len(graph_ids))
    with psycopg.connect(**_database_config()) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '120s'")
            graphs = connection.execute(
                f"SELECT graphid::text, is_active FROM graphs WHERE graphid IN ({placeholders})",
                graph_ids,
            ).fetchall()
            nodes = connection.execute(
                "SELECT nodeid::text, nodegroupid::text, datatype, name FROM nodes WHERE graphid = %s",
                (profile.graph_id,),
            ).fetchall()
            edges = connection.execute(
                "SELECT domainnodeid::text, rangenodeid::text FROM edges WHERE graphid = %s",
                (profile.graph_id,),
            ).fetchall()
            resources = connection.execute(
                "SELECT resourceinstanceid::text, graphid::text, createdtime, descriptors, name "
                f"FROM resource_instances WHERE graphid IN ({placeholders})",
                graph_ids,
            ).fetchall()
            tiles = connection.execute(
                "SELECT resourceinstanceid::text, nodegroupid::text, tiledata FROM tiles "
                "WHERE resourceinstanceid IN (SELECT resourceinstanceid FROM resource_instances "
                f"WHERE graphid IN ({placeholders})) ORDER BY sortorder, tileid",
                graph_ids,
            ).fetchall()
    return build_resource_snapshot(profile, graphs, nodes, edges, resources, tiles)


def load_snapshot() -> Snapshot:
    """Compatibility loader for the current Context API."""
    normalized = load_resource_snapshot(CONTEXT_PROFILE)
    nodes = [
        {
            "nodeid": node.node_id,
            "nodegroupid": node.nodegroup_id,
            "datatype": node.datatype,
            "name": node.name,
        }
        for node in normalized.nodes.values()
    ]
    edges = [
        {"domainnodeid": domain, "rangenodeid": range_}
        for domain, range_ in normalized.edges
    ]
    return _context_snapshot(normalized, nodes, edges)
