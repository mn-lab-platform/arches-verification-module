"""Read Arches graph metadata for the future rule builder."""

from uuid import UUID

from .profiles import ResourceProfile
from .repository import DataModelError, _database_config, localized

RELATION_DATATYPES = {"resource-instance", "resource-instance-list"}
NUMBER_DATATYPES = {"number", "string", "non-localized-string"}
GROUP_DATATYPES = NUMBER_DATATYPES | {"boolean", "concept", "domain-value", "date", "edtf"}
GEOMETRY_DATATYPE = "geojson-feature-collection"


def _graph_ids(config: object) -> set[str]:
    """Ignore malformed graph references instead of passing them to a UUID query."""
    if not isinstance(config, dict) or not isinstance(config.get("graphs"), list):
        return set()
    graph_ids = set()
    for graph in config["graphs"]:
        if isinstance(graph, dict):
            try:
                graph_ids.add(str(UUID(str(graph["graphid"]))))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
    return graph_ids


def _field(node: dict) -> dict:
    return {
        "node_id": node["nodeid"],
        "label": localized(node["name"]) or node["nodeid"],
        "datatype": node["datatype"],
        "nodegroup_id": node["nodegroupid"],
    }


def build_rule_builder_options(profile: ResourceProfile, graphs: list[dict], nodes: list[dict]) -> dict:
    """Present only nodes compatible with each existing rule factory."""
    graph_names = {
        graph["graphid"]: localized(graph["name"]) or graph["graphid"]
        for graph in graphs if graph["is_active"] and graph["isresource"]
    }
    if profile.graph_id not in graph_names:
        raise DataModelError(f"Nieaktywny lub brakujący graf: {profile.label}")

    nodes_by_graph: dict[str, list[dict]] = {}
    nodes_by_id = {}
    for node in nodes:
        nodes_by_graph.setdefault(node["graphid"], []).append(node)
        nodes_by_id[node["nodeid"]] = node

    main_nodes = nodes_by_graph.get(profile.graph_id, [])
    fields = [_field(node) for node in main_nodes if node["datatype"] != "semantic" and node["nodegroupid"]]
    numbering = [_field(node) for node in main_nodes if node["datatype"] in NUMBER_DATATYPES and node["nodegroupid"]]
    grouping_fields = [_field(node) for node in main_nodes if node["datatype"] in GROUP_DATATYPES and node["nodegroupid"]]

    aliases = {
        (relation.direction, relation.node_id, relation.graph_id): alias
        for alias, relation in profile.related_graphs.items()
    }
    relations = []
    for node in main_nodes:
        if node["datatype"] not in RELATION_DATATYPES or not node["nodegroupid"]:
            continue
        targets = _graph_ids(node["config"])
        relations.append({
            "id": f"out:{node['nodeid']}",
            "alias": next((alias for (direction, node_id, _), alias in aliases.items()
                           if direction == "outgoing" and node_id == node["nodeid"]), None),
            "node_id": node["nodeid"],
            "label": localized(node["name"]) or node["nodeid"],
            "datatype": node["datatype"],
            "direction": "outgoing",
            "source_graph_id": profile.graph_id,
            "target_graphs": [
                {"graph_id": graph_id, "name": graph_names[graph_id]}
                for graph_id in sorted(targets) if graph_id in graph_names
            ],
            "any_resource_type": not targets,
        })

    for alias, relation in profile.related_graphs.items():
        if relation.direction != "incoming" or not relation.graph_id:
            continue
        node = nodes_by_id.get(relation.node_id)
        if (node is None or node["graphid"] != relation.graph_id
                or node["datatype"] not in RELATION_DATATYPES
                or relation.graph_id not in graph_names):
            raise DataModelError(f"Niepoprawna relacja przychodząca: {alias}")
        relations.append({
            "id": f"in:{relation.graph_id}:{relation.node_id}",
            "alias": alias,
            "node_id": node["nodeid"],
            "label": localized(node["name"]) or node["nodeid"],
            "datatype": node["datatype"],
            "direction": "incoming",
            "source_graph_id": relation.graph_id,
            "target_graphs": [{"graph_id": profile.graph_id, "name": graph_names[profile.graph_id]}],
            "any_resource_type": False,
        })

    related_graph_ids = {
        graph["graph_id"] for relation in relations for graph in relation["target_graphs"]
        if relation["direction"] == "outgoing"
    }
    geometries = {
        "source": [_field(node) for node in main_nodes if node["datatype"] == GEOMETRY_DATATYPE],
        "targets": [
            {**_field(node), "graph_id": graph_id, "graph_name": graph_names[graph_id]}
            for graph_id in sorted(related_graph_ids)
            for node in nodes_by_graph.get(graph_id, [])
            if node["datatype"] == GEOMETRY_DATATYPE
        ],
    }

    sort_by_label = lambda item: (item["label"].casefold(), item["node_id"])
    for choices in (fields, numbering, grouping_fields, geometries["source"]):
        choices.sort(key=sort_by_label)
    relations.sort(key=lambda item: (item["label"].casefold(), item["direction"], item["node_id"]))
    geometries["targets"].sort(key=lambda item: (item["graph_name"].casefold(), item["label"].casefold()))
    return {
        "model": {"resource_type": profile.id, "graph_id": profile.graph_id, "name": profile.label},
        "fields": fields,
        "numbering": numbering,
        "grouping": {"fields": grouping_fields, "relations": relations},
        "relations": relations,
        "geometries": geometries,
    }


def load_rule_builder_options(profile: ResourceProfile) -> dict:
    """Use one read-only transaction for graph, relation and node definitions."""
    import psycopg

    with psycopg.connect(**_database_config()) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '120s'")
            main_nodes = connection.execute(
                "SELECT nodeid::text, graphid::text, nodegroupid::text, datatype, name, config "
                "FROM nodes WHERE graphid = %s",
                (profile.graph_id,),
            ).fetchall()
            graph_ids = {profile.graph_id}
            graph_ids.update(
                relation.graph_id for relation in profile.related_graphs.values() if relation.graph_id
            )
            for node in main_nodes:
                if node["datatype"] in RELATION_DATATYPES:
                    graph_ids.update(_graph_ids(node["config"]))

            graphs = connection.execute(
                "SELECT graphid::text, name, is_active, isresource FROM graphs "
                "WHERE graphid = ANY(%s::uuid[])",
                (list(graph_ids),),
            ).fetchall()
            other_nodes = connection.execute(
                "SELECT nodeid::text, graphid::text, nodegroupid::text, datatype, name, config "
                "FROM nodes WHERE graphid = ANY(%s::uuid[])",
                (list(graph_ids - {profile.graph_id}),),
            ).fetchall()
    return build_rule_builder_options(profile, graphs, main_nodes + other_nodes)
