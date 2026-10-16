"""Cache offline feed ranking to reduce repeated Amazon Personalize calls.

Keyed by viewer id only so paging / swipes reuse one Personalize ranking for
the TTL window. Redis is optional (REDIS_URL); without it the cache is
in-process RAM and is still useful on the same gunicorn worker.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

RankedEntry = Tuple[int, float, dict]
RankedPayload = Tuple[List[RankedEntry], str]


class OfflineFeedCache:
    def __init__(self) -> None:
        self.enabled = os.getenv("OFFLINE_FEED_CACHE_ENABLED", "true").lower() == "true"
        self.ttl_seconds = int(os.getenv("OFFLINE_FEED_CACHE_TTL", "600"))
        self._memory: Dict[str, Tuple[float, RankedPayload]] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._redis_prefix = os.getenv("OFFLINE_FEED_CACHE_PREFIX", "vyb:offline_feed:")
        self._init_redis()

    def _init_redis(self) -> None:
        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            return
        try:
            import redis

            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            logger.info("Offline feed cache using Redis")
        except Exception as exc:
            logger.warning("Redis unavailable for offline feed cache: %s", exc)
            self._redis = None

    def make_key(self, viewer_id: int, *args, **kwargs) -> str:
        return str(int(viewer_id))

    def get_ranked(self, cache_key: str) -> Optional[RankedPayload]:
        if not self.enabled:
            return None

        redis_key = f"{self._redis_prefix}{cache_key}"
        if self._redis is not None:
            try:
                raw = self._redis.get(redis_key)
                if raw:
                    payload = json.loads(raw)
                    ranked = [
                        (int(uid), float(score), dict(bd))
                        for uid, score, bd in payload["ranked"]
                    ]
                    return ranked, payload["ranker"]
            except Exception as exc:
                logger.warning("Offline feed cache Redis read failed: %s", exc)

        with self._lock:
            item = self._memory.get(cache_key)
            if not item:
                return None
            expires_at, payload = item
            if time.time() >= expires_at:
                self._memory.pop(cache_key, None)
                return None
            return payload

    def set_ranked(self, cache_key: str, ranked: List[RankedEntry], ranker: str) -> None:
        if not self.enabled:
            return

        payload: RankedPayload = (ranked, ranker)
        redis_key = f"{self._redis_prefix}{cache_key}"
        serialized = json.dumps({
            "ranker": ranker,
            "ranked": [[uid, score, bd] for uid, score, bd in ranked],
        })

        if self._redis is not None:
            try:
                self._redis.setex(redis_key, self.ttl_seconds, serialized)
                return
            except Exception as exc:
                logger.warning("Offline feed cache Redis write failed: %s", exc)

        with self._lock:
            self._memory[cache_key] = (time.time() + self.ttl_seconds, payload)

    def invalidate_viewer(self, viewer_id: int) -> None:
        viewer_key = str(int(viewer_id))
        if self._redis is not None:
            try:
                keys = [f"{self._redis_prefix}{viewer_key}"]
                keys.extend(self._redis.scan_iter(f"{self._redis_prefix}{viewer_key}:*"))
                if keys:
                    self._redis.delete(*keys)
            except Exception as exc:
                logger.warning("Offline feed cache Redis invalidate failed: %s", exc)

        needle = f"{viewer_key}:"
        with self._lock:
            self._memory.pop(viewer_key, None)
            for key in list(self._memory.keys()):
                if key.startswith(needle):
                    self._memory.pop(key, None)


_CACHE: Optional[OfflineFeedCache] = None


def get_offline_feed_cache() -> OfflineFeedCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = OfflineFeedCache()
    return _CACHE
