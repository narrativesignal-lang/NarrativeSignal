from __future__ import annotations

import logging
import time

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_PAUSE_UNTIL_KEY = "market:v1:massive_pause_until_ts"
_CONSEC_FAIL_KEY = "market:v1:massive_consecutive_fail_count"


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def massive_paused() -> bool:
    try:
        raw = _r().get(_PAUSE_UNTIL_KEY)
        if not raw:
            return False
        return time.time() < float(raw)
    except Exception:
        return False


def _pause_seconds_for_fail(n: int) -> int:
    if n <= 1:
        return 600
    if n == 2:
        return 3600
    if n == 3:
        return 6 * 3600
    return 24 * 3600


def massive_mark_failure(reason: str | None = None) -> tuple[int, int]:
    """Increment consecutive fails and pause accordingly. Returns (fail_count, pause_seconds)."""
    try:
        r = _r()
        n = int(r.incr(_CONSEC_FAIL_KEY))
        sec = _pause_seconds_for_fail(n)
        until = time.time() + sec
        r.setex(_PAUSE_UNTIL_KEY, sec + 120, str(until))
        logger.warning("massive_guard pause seconds=%s fail_count=%s reason=%s", sec, n, reason or "-")
        return n, sec
    except Exception:
        return 1, 600


def massive_mark_success() -> None:
    try:
        r = _r()
        r.delete(_CONSEC_FAIL_KEY)
        r.delete(_PAUSE_UNTIL_KEY)
    except Exception:
        pass

