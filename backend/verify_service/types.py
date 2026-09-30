from dataclasses import asdict, dataclass, field
from typing import Any


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
