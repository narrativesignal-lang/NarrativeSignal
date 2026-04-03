"""
Global hard quotas for Massive REST usage (shared across workers).

Acquire quota only through ``app.services.massive_api_client`` (which calls this module before any GET).
Do not call ``massive_quota_try_acquire`` and then issue HTTP to Massive elsewhere — that bypass is forbidden.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Literal

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

SkipReason = Literal["massive_quota_per_minute", "massive_quota_per_day"]

# Redis keys (UTC buckets)
_MINUTE_KEY_TMPL = "market:v1:massive_quota:minute:{}"  # YYYYMMDDHHMM
_DAY_KEY_TMPL = "market:v1:massive_quota:day:{}"  # YYYYMMDD

# Lua: atomically reserve ``count`` slots; roll back if either limit would be exceeded.
_ACQUIRE_LUA = """
local min_key = KEYS[1]
local day_key = KEYS[2]
local count = tonumber(ARGV[1])
if count == nil or count < 1 then count = 1 end
local min_limit = tonumber(ARGV[2])
local day_limit = tonumber(ARGV[3])

local m = redis.call('INCRBY', min_key, count)
redis.call('EXPIRE', min_key, 180)
if m > min_limit then
  redis.call('INCRBY', min_key, -count)
  return {0, 'massive_quota_per_minute'}
end

local d = redis.call('INCRBY', day_key, count)
redis.call('EXPIRE', day_key, 259200)
if d > day_limit then
  redis.call('INCRBY', min_key, -count)
  redis.call('INCRBY', day_key, -count)
  return {0, 'massive_quota_per_day'}
end

return {1, 'ok'}
"""


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _minute_bucket_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


def _day_bucket_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def massive_quota_try_acquire(*, count: int = 1, log_context: str | None = None) -> SkipReason | None:
    """
    Reserve ``count`` Massive API units for the current UTC minute/day.

    Returns None on success, or a skip reason string (log exactly this; do not retry in-run).
    """
    cnt = max(1, int(count))
    per_min = max(1, int(getattr(settings, "massive_quota_per_minute", 30)))
    per_day = max(1, int(getattr(settings, "massive_quota_per_day", 2000)))
    min_key = _MINUTE_KEY_TMPL.format(_minute_bucket_utc())
    day_key = _DAY_KEY_TMPL.format(_day_bucket_utc())
    ctx = log_context or "massive"
    try:
        client = _r()
        res = client.eval(_ACQUIRE_LUA, 2, min_key, day_key, str(cnt), str(per_min), str(per_day))
        if not res or len(res) < 2:
            logger.warning(
                "job=massive_quota %s result=unexpected_lua count=%s",
                ctx,
                cnt,
            )
            return "massive_quota_per_minute"
        ok = int(res[0]) == 1
        if ok:
            return None
        reason = str(res[1])
        if reason == "massive_quota_per_minute":
            logger.info(
                "job=massive_quota %s skipped_due_to_per_minute_limit=1 count_requested=%s per_minute_limit=%s",
                ctx,
                cnt,
                per_min,
            )
            return "massive_quota_per_minute"
        if reason == "massive_quota_per_day":
            logger.info(
                "job=massive_quota %s skipped_due_to_per_day_limit=1 count_requested=%s per_day_limit=%s",
                ctx,
                cnt,
                per_day,
            )
            return "massive_quota_per_day"
        logger.warning("job=massive_quota %s unknown_reason=%s", ctx, reason)
        return "massive_quota_per_minute"
    except Exception as e:
        logger.warning("job=massive_quota %s redis_error=%s — treating as blocked", ctx, str(e)[:200])
        return "massive_quota_per_minute"
