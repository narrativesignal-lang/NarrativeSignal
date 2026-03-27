"""Best-effort Redis counters for outbound (non-DB) API usage."""

from __future__ import annotations

import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


def bump(kind: str, n: int = 1) -> None:
    if n <= 0:
        return
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.incrby(f"stats:external_api:{kind}", n)
    except Exception as e:
        logger.debug("external_api_stats bump %s failed: %s", kind, e)
