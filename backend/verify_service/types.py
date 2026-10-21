from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NodeDefinition:
    node_id: str
    nodegroup_id: str | None
    datatype: str
    name: Any


@dataclass
class RelationState:
    target_ids: list[str] = field(default_factory=list)
    valid_target_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationState":
        return cls(**data)


@dataclass
class SpatialMatch:
    target_id: str
    source_has_geometry: bool
    target_has_geometry: bool
    within: bool


@dataclass
class ResourceFact:
    resource_id: str
    name: str
    created_at: str
    fields: dict[str, list[Any]] = field(default_factory=dict)
    relations: dict[str, RelationState] = field(default_factory=dict)
    group_values: dict[str, list[dict[str, bool]]] = field(default_factory=dict)
    spatial: dict[str, list[SpatialMatch]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceFact":
        return cls(
            resource_id=data["resource_id"],
            name=data["name"],
            created_at=data["created_at"],
            fields=data.get("fields", {}),
            relations={key: RelationState.from_dict(value) for key, value in data.get("relations", {}).items()},
            group_values=data.get("group_values", {}),
            spatial={key: [SpatialMatch(**match) for match in matches] for key, matches in data.get("spatial", {}).items()},
        )


@dataclass
class ResourceSnapshot:
    resource_type: str
    graph_id: str
    generated_at: str
    nodes: dict[str, NodeDefinition]
    edges: list[tuple[str, str]]
    related_resources: dict[str, dict[str, str]]
    resources: dict[str, ResourceFact]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceSnapshot":
        return cls(
            resource_type=data["resource_type"],
            graph_id=data["graph_id"],
            generated_at=data["generated_at"],
            nodes={key: NodeDefinition(**value) for key, value in data["nodes"].items()},
            edges=[tuple(edge) for edge in data["edges"]],
            related_resources=data["related_resources"],
            resources={key: ResourceFact.from_dict(value) for key, value in data["resources"].items()},
        )
