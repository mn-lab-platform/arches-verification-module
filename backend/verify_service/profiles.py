"""Hardcoded resource catalog for future rule and loader factories."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from .constants import (
    CONTEXT_COMMENT_NODE_ID,
    CONTEXT_DESCRIPTIVE_INFORMATION_NODE_ID,
    CONTEXT_GRAPH_ID,
    CONTEXT_HARRIS_ABOVE_NODE_ID,
    CONTEXT_HARRIS_BELOW_NODE_ID,
    CONTEXT_HARRIS_SAME_LEVEL_NODE_ID,
    CONTEXT_NUMBER_NODE_ID,
    CONTEXT_PHOTOS_OR_DRAWINGS_NODE_ID,
    CONTEXT_SPATIAL_EXTENT_NODE_ID,
    CONTEXT_TRENCH_NODE_ID,
    IIIF_CONTEXT_NODE_ID,
    IIIF_GRAPH_ID,
    MODEL_3D_CONTEXT_NODE_ID,
    MODEL_3D_GRAPH_ID,
    POTTERY_CONTEXT_NODE_ID,
    POTTERY_GRAPH_ID,
    TRENCH_GRAPH_ID,
)


@dataclass(frozen=True)
class RelationProfile:
    """A relation node on the main graph (outgoing) or related graph (incoming)."""

    graph_id: str
    node_id: str
    direction: Literal["outgoing", "incoming"]


@dataclass(frozen=True)
class ResourceProfile:
    id: str
    label: str
    graph_id: str
    fields: Mapping[str, str]
    related_graphs: Mapping[str, RelationProfile]
    completeness_excluded_roots: Mapping[str, str]
    completeness_optional_fields: Mapping[str, str]


CONTEXT_PROFILE = ResourceProfile(
    id="context",
    label="(O) Context",
    graph_id=CONTEXT_GRAPH_ID,
    fields=MappingProxyType({
        "number": CONTEXT_NUMBER_NODE_ID,
        "trench": CONTEXT_TRENCH_NODE_ID,
        "harris_above": CONTEXT_HARRIS_ABOVE_NODE_ID,
        "harris_below": CONTEXT_HARRIS_BELOW_NODE_ID,
        "harris_same_level": CONTEXT_HARRIS_SAME_LEVEL_NODE_ID,
    }),
    related_graphs=MappingProxyType({
        "trench": RelationProfile(TRENCH_GRAPH_ID, CONTEXT_TRENCH_NODE_ID, "outgoing"),
        "harris_above": RelationProfile(CONTEXT_GRAPH_ID, CONTEXT_HARRIS_ABOVE_NODE_ID, "outgoing"),
        "harris_below": RelationProfile(CONTEXT_GRAPH_ID, CONTEXT_HARRIS_BELOW_NODE_ID, "outgoing"),
        "harris_same_level": RelationProfile(CONTEXT_GRAPH_ID, CONTEXT_HARRIS_SAME_LEVEL_NODE_ID, "outgoing"),
        "3d": RelationProfile(MODEL_3D_GRAPH_ID, MODEL_3D_CONTEXT_NODE_ID, "incoming"),
        "iiif": RelationProfile(IIIF_GRAPH_ID, IIIF_CONTEXT_NODE_ID, "incoming"),
        "pottery": RelationProfile(POTTERY_GRAPH_ID, POTTERY_CONTEXT_NODE_ID, "incoming"),
    }),
    completeness_excluded_roots=MappingProxyType({
        "harris_above": CONTEXT_HARRIS_ABOVE_NODE_ID,
        "harris_below": CONTEXT_HARRIS_BELOW_NODE_ID,
        "harris_same_level": CONTEXT_HARRIS_SAME_LEVEL_NODE_ID,
        "photos_or_drawings": CONTEXT_PHOTOS_OR_DRAWINGS_NODE_ID,
        "spatial_extent": CONTEXT_SPATIAL_EXTENT_NODE_ID,
        "descriptive_information": CONTEXT_DESCRIPTIVE_INFORMATION_NODE_ID,
    }),
    completeness_optional_fields=MappingProxyType({
        "comment": CONTEXT_COMMENT_NODE_ID,
    }),
)

PROFILES: Mapping[str, ResourceProfile] = MappingProxyType({
    CONTEXT_PROFILE.id: CONTEXT_PROFILE,
})
