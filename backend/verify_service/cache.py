"""A single, bounded, five-minute snapshot in the existing Redis instance."""

import json
import logging
import os
import zlib
from collections.abc import Callable
from typing import Any

from .constants import SNAPSHOT_CACHE_KEY, SNAPSHOT_TTL_SECONDS
from .types import Snapshot

logger = logging.getLogger(__name__)


def cached_snapshot(loader: Callable[[], Snapshot], client: Any = None) -> Snapshot:
    if client is None:
        try:
            import redis

            client = redis.Redis.from_url(
                os.environ.get("VERIFY_REDIS_URL", "redis://arches_redis:6379/2"),
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception as error:
            logger.warning("Redis unavailable; loading Context from PostgreSQL: %s", error)
            return loader()

    try:
        raw = client.get(SNAPSHOT_CACHE_KEY)
        if raw:
            return Snapshot.from_dict(json.loads(zlib.decompress(raw)))
    except Exception as error:
        logger.warning("Context cache read failed; rebuilding: %s", error)

    snapshot = loader()
    try:
        payload = zlib.compress(json.dumps(snapshot.to_dict(), ensure_ascii=False).encode("utf-8"))
        client.set(SNAPSHOT_CACHE_KEY, payload, ex=SNAPSHOT_TTL_SECONDS)
    except Exception as error:
        logger.warning("Context cache write failed; using fresh PostgreSQL data: %s", error)
    return snapshot
