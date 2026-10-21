"""Hardcoded resource catalog for future rule and loader factories."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

from .constants import (
    ANNOTATION_GRAPH_ID,
    ANNOTATION_RESOURCE_NODE_ID,
    CONTEXT_COMMENT_NODE_ID,
    CONTEXT_FOOTPRINT_NODE_ID,
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
    MODEL_3D_GEOSPATIAL_NODE_ID,
    MODEL_3D_GRAPH_ID,
    POTTERY_CONTEXT_NODE_ID,
    POTTERY_DIAGNOSTIC_NODE_ID,
    POTTERY_GRAPH_ID,
    POTTERY_TYPE_NODE_ID,
    POTTERY_UNDIAGNOSTIC_NODE_ID,
    SPECIAL_FIND_CATEGORY_NODE_ID,
    SPECIAL_FIND_CONTEXT_NODE_ID,
    SPECIAL_FIND_GRAPH_ID,
    SPECIAL_FIND_NUMBER_NODE_ID,
    SPECIAL_FIND_ORDER_NODE_ID,
    SPECIAL_FIND_POSITION_NODE_ID,
    SPECIAL_FIND_PREFIX_NODE_ID,
    TRENCH_GRAPH_ID,
    TRENCH_FOOTPRINT_NODE_ID,
)


@dataclass(frozen=True)
class RelationProfile:
    """A relation node on the main graph (outgoing) or related graph (incoming)."""

    graph_id: str | None  # None means any existing Arches resource graph.
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
    spatial_nodes: Mapping[str, str] = field(default_factory=dict)


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

SPECIAL_FIND_PROFILE = ResourceProfile(
    id="special_find", label="(O) Special find", graph_id=SPECIAL_FIND_GRAPH_ID,
    fields=MappingProxyType({
        "number": SPECIAL_FIND_NUMBER_NODE_ID,
        "prefix": SPECIAL_FIND_PREFIX_NODE_ID,
        "order_number": SPECIAL_FIND_ORDER_NODE_ID,
        "category": SPECIAL_FIND_CATEGORY_NODE_ID,
    }),
    related_graphs=MappingProxyType({
        "context": RelationProfile(CONTEXT_GRAPH_ID, SPECIAL_FIND_CONTEXT_NODE_ID, "outgoing"),
        "trench": RelationProfile(TRENCH_GRAPH_ID, "a0d4f084-67f2-4c31-919e-5e55f5852490", "outgoing"),
    }),
    completeness_excluded_roots=MappingProxyType({}),
    completeness_optional_fields=MappingProxyType({}),
    spatial_nodes=MappingProxyType({
        "self": SPECIAL_FIND_POSITION_NODE_ID,
        "context": CONTEXT_FOOTPRINT_NODE_ID,
        "trench": TRENCH_FOOTPRINT_NODE_ID,
    }),
)

MODEL_3D_PROFILE = ResourceProfile(
    id="digital_3d", label="(O) Digital Resource 3D", graph_id=MODEL_3D_GRAPH_ID,
    fields=MappingProxyType({"geospatial": MODEL_3D_GEOSPATIAL_NODE_ID}),
    related_graphs=MappingProxyType({
        "related": RelationProfile(None, MODEL_3D_CONTEXT_NODE_ID, "outgoing"),
    }),
    completeness_excluded_roots=MappingProxyType({}),
    completeness_optional_fields=MappingProxyType({}),
)

IIIF_PROFILE = ResourceProfile(
    id="digital_iiif", label="(O) Digital Resource IIIF", graph_id=IIIF_GRAPH_ID,
    fields=MappingProxyType({}),
    related_graphs=MappingProxyType({
        "related": RelationProfile(None, IIIF_CONTEXT_NODE_ID, "outgoing"),
    }),
    completeness_excluded_roots=MappingProxyType({}),
    completeness_optional_fields=MappingProxyType({}),
)

ANNOTATION_PROFILE = ResourceProfile(
    id="annotation", label="(O) Annotation", graph_id=ANNOTATION_GRAPH_ID,
    fields=MappingProxyType({}),
    related_graphs=MappingProxyType({
        "related": RelationProfile(None, ANNOTATION_RESOURCE_NODE_ID, "outgoing"),
    }),
    completeness_excluded_roots=MappingProxyType({}),
    completeness_optional_fields=MappingProxyType({}),
)

POTTERY_PROFILE = ResourceProfile(
    id="pottery_collection", label="(O) Pottery Collection", graph_id=POTTERY_GRAPH_ID,
    fields=MappingProxyType({
        "category": POTTERY_TYPE_NODE_ID,
        "diagnostic": POTTERY_DIAGNOSTIC_NODE_ID,
        "undiagnostic": POTTERY_UNDIAGNOSTIC_NODE_ID,
    }),
    related_graphs=MappingProxyType({
        "context": RelationProfile(CONTEXT_GRAPH_ID, POTTERY_CONTEXT_NODE_ID, "outgoing"),
    }),
    completeness_excluded_roots=MappingProxyType({}),
    completeness_optional_fields=MappingProxyType({}),
)

# Six Arches Pottery Record graphs share the same rule; only graph and node IDs differ.
POTTERY_RECORD_MODELS = (
    ("pottery_amphorae", "(O) Pottery Record - Amphorae", "c09880b6-f404-4747-8038-a53938093437", "5fa2dbcf-0e8e-4abd-81e5-a9304350da91"),
    ("pottery_kitchen_ware", "(O) Pottery Record - Kitchen Ware", "9a8bf6db-3e28-4528-81b6-d394f9e72cc7", "762be0c9-8417-46d8-b3cd-04f3b44753d7"),
    ("pottery_lamps", "(O) Pottery Record - Lamps", "61b403ae-906c-4cba-ab64-8393c91561d1", "5a270090-4d63-4086-9f7b-7b5cba39d917"),
    ("pottery_plain_ware", "(O) Pottery Record - Plain Ware", "08c52b0f-c734-455b-aaef-e2f70ddae793", "fd7451a5-d754-4bc3-a613-57fd229e22fe"),
    ("pottery_storage_vessels", "(O) Pottery Record - Storage Vessels", "aeeea75c-9251-45fe-9fa6-85e5153e9091", "7ac51ec0-67f6-42ae-96f1-662dd53815df"),
    ("pottery_table_ware", "(O) Pottery Record - Table Ware", "124255a2-f11d-4a52-94f4-a06b791c4a60", "e875de72-6540-470d-b188-3e0323832ac1"),
)

POTTERY_RECORD_PROFILES = tuple(
    ResourceProfile(
        id=resource_type, label=label, graph_id=graph_id,
        fields=MappingProxyType({}),
        related_graphs=MappingProxyType({
            "pottery_collection": RelationProfile(POTTERY_GRAPH_ID, relation_node_id, "outgoing"),
        }),
        completeness_excluded_roots=MappingProxyType({}),
        completeness_optional_fields=MappingProxyType({}),
    )
    for resource_type, label, graph_id, relation_node_id in POTTERY_RECORD_MODELS
)

PROFILES: Mapping[str, ResourceProfile] = MappingProxyType({
    profile.id: profile for profile in (
        CONTEXT_PROFILE, SPECIAL_FIND_PROFILE, MODEL_3D_PROFILE, IIIF_PROFILE,
        ANNOTATION_PROFILE, POTTERY_PROFILE, *POTTERY_RECORD_PROFILES,
    )
})
