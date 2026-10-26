"""Five-minute Redis snapshots, keyed by resource profile."""

import hashlib
import json
import logging
import os
import zlib
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from .constants import SNAPSHOT_CACHE_PREFIX, SNAPSHOT_TTL_SECONDS
from .profiles import ResourceProfile
from .types import ResourceSnapshot

logger = logging.getLogger(__name__)


def profile_fingerprint(profile: ResourceProfile) -> str:
    """Custom rules extend profiles, so the snapshot key follows everything the loader reads."""
    shape = {
        "fields": dict(profile.fields),
        "related_graphs": {alias: asdict(relation) for alias, relation in profile.related_graphs.items()},
        "completeness_excluded_roots": dict(profile.completeness_excluded_roots),
        "completeness_optional_fields": dict(profile.completeness_optional_fields),
        "spatial_nodes": dict(profile.spatial_nodes),
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def cached_resource_snapshot(
    profile: ResourceProfile,
    loader: Callable[[ResourceProfile], ResourceSnapshot],
    client: Any = None,
) -> ResourceSnapshot:
    """Use a fresh database read on a miss; never return an expired snapshot."""
    if client is None:
        try:
            import redis

            client = redis.Redis.from_url(
                os.environ.get("VERIFY_REDIS_URL", "redis://arches_redis:6379/2"),
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception as error:
            logger.warning("Redis unavailable; loading %s from PostgreSQL: %s", profile.id, error)
            return loader(profile)

    key = f"{SNAPSHOT_CACHE_PREFIX}{profile.id}:{profile_fingerprint(profile)}"
    try:
        raw = client.get(key)
        if raw:
            snapshot = ResourceSnapshot.from_dict(json.loads(zlib.decompress(raw)))
            if snapshot.resource_type == profile.id and snapshot.graph_id == profile.graph_id:
                return snapshot
            logger.warning("Cache profile mismatch for %s; rebuilding", profile.id)
    except Exception as error:
        logger.warning("%s cache read failed; rebuilding: %s", profile.id, error)

    snapshot = loader(profile)
    try:
        payload = zlib.compress(json.dumps(snapshot.to_dict(), ensure_ascii=False).encode("utf-8"))
        client.set(key, payload, ex=SNAPSHOT_TTL_SECONDS)
    except Exception as error:
        logger.warning("%s cache write failed; using fresh PostgreSQL data: %s", profile.id, error)
    return snapshot
