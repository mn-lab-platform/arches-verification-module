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
class ResourceFact:
    resource_id: str
    name: str
    created_at: str
    fields: dict[str, list[Any]] = field(default_factory=dict)
    relations: dict[str, RelationState] = field(default_factory=dict)
    group_values: dict[str, list[dict[str, bool]]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceFact":
        return cls(
            resource_id=data["resource_id"],
            name=data["name"],
            created_at=data["created_at"],
            fields=data.get("fields", {}),
            relations={key: RelationState.from_dict(value) for key, value in data.get("relations", {}).items()},
            group_values=data.get("group_values", {}),
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


@dataclass
class ContextFact:
    resource_id: str
    name: str
    created_at: str
    trench_id: str | None
    trench_issue: str | None
    number: int | None
    number_issue: str | None
    harris_ids: list[str] = field(default_factory=list)
    completeness_issues: list[str] = field(default_factory=list)
    has_3d: bool = False
    has_iiif: bool = False
    has_pottery: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextFact":
        return cls(**data)


@dataclass
class Snapshot:
    generated_at: str
    trenches: dict[str, str]
    contexts: dict[str, ContextFact]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Snapshot":
        return cls(
            generated_at=data["generated_at"],
            trenches=data["trenches"],
            contexts={key: ContextFact.from_dict(value) for key, value in data["contexts"].items()},
        )
