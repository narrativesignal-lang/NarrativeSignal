"""
Rate limiting V1 — Redis fixed-window counters (per minute).

Tunables: RATE_LIMIT_* below. Future: read per-user tier from JWT/cache and override limits.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis.asyncio as redis
from jose import JWTError

from app.core.config import settings
from app.core.security import decode_token

logger = logging.getLogger(__name__)

# --- Tunable limits (extend later, e.g. premium multipliers) -----------------
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_IP_PER_MINUTE = 60
RATE_LIMIT_USER_PER_MINUTE = 120
REDIS_KEY_TTL_SEC = 120  # > window so keys expire after the minute bucket ends

REDIS_KEY_PREFIX = "rl:v1"

# Atomic INCR + EXPIRE on first hit; return 1 if exceeded else 0
_LUA_INCR_CHECK = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
if c > tonumber(ARGV[1]) then
  return 1
end
return 0
"""

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _window_id() -> int:
    return int(time.time()) // RATE_LIMIT_WINDOW_SEC


def client_ip_from_scope(headers: list[tuple[bytes, bytes]], client: Any) -> str:
    """Prefer X-Forwarded-For first hop when behind a reverse proxy."""
    hdr = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in headers}
    xff = hdr.get("x-forwarded-for")
    if xff:
        part = xff.split(",")[0].strip()
        if part:
            return part[:128]
    if client and getattr(client, "host", None):
        return str(client.host)[:128]
    return "unknown"


def _bearer_user_id(auth_header: str | None) -> str | None:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            return None
        uid = payload.get("uid")
        if uid and isinstance(uid, str):
            return uid[:64]
    except JWTError:
        return None
    return None


async def enforce_rate_limits(
    *,
    client_ip: str,
    authorization_header: str | None,
) -> bool:
    """
    Returns True if the request should be allowed, False if rate limited (429).

    - Always applies IP bucket (anonymous + authenticated).
    - If a valid access JWT is present, also applies per-user bucket.
    """
    try:
        r = _get_redis()
    except Exception as e:
        logger.warning("rate_limit: redis client failed (fail-open): %s", e)
        return True

    wid = _window_id()
    try:
        ip_key = f"{REDIS_KEY_PREFIX}:ip:{client_ip}:{wid}"
        exceeded = await r.eval(
            _LUA_INCR_CHECK, 1, ip_key, str(RATE_LIMIT_IP_PER_MINUTE), str(REDIS_KEY_TTL_SEC)
        )
        if int(exceeded):
            return False

        user_id = _bearer_user_id(authorization_header)
        if user_id:
            user_key = f"{REDIS_KEY_PREFIX}:user:{user_id}:{wid}"
            exceeded_u = await r.eval(
                _LUA_INCR_CHECK,
                1,
                user_key,
                str(RATE_LIMIT_USER_PER_MINUTE),
                str(REDIS_KEY_TTL_SEC),
            )
            if int(exceeded_u):
                return False
    except Exception as e:
        logger.warning("rate_limit: redis op failed (fail-open): %s", e)
        return True

    return True
