"""
Rate limiting — Redis fixed-window INCR + EXPIRE (async).

- Anonymous: 60 req/min by IP (`ip:*`).
- Authenticated: 120 req/min by `user_id` only (no parallel IP bucket).
- Stricter: `/api/macro/news` and `/api/entities*` at 30 req/min (`endpoint:*`).
- Register / login: separate per-path Redis windows by IP (`auth:*`), do not consume the general IP bucket.
  Register allows bursts suitable for register+immediate login; stricter in production than in dev.

Redis errors → fail-open (allow). Uses redis.asyncio via get_async_redis().
"""

from __future__ import annotations

import logging
import time
from typing import Any

from jose import JWTError

from app.core.config import settings
from app.core.redis_async import get_async_redis
from app.core.security import decode_token

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_IP_PER_MINUTE = 60
RATE_LIMIT_USER_PER_MINUTE = 120
RATE_LIMIT_STRICT_PER_MINUTE = 30
AUTH_PATH_REGISTER = "/api/auth/register"
AUTH_PATH_LOGIN = "/api/auth/login"
# Sliding windows per path (seconds, max_requests) — only IP bucket for these paths.
_AUTH_RELAX_ENV = frozenset({"dev", "development", "test", "local"})


def _relaxed_auth_limits() -> bool:
    return (getattr(settings, "env", "dev") or "dev").strip().lower() in _AUTH_RELAX_ENV


def _auth_path_limits(path: str) -> tuple[int, int] | None:
    """(window_sec, max_hits) for dedicated auth bucket, or None if not an auth public path."""
    if path == AUTH_PATH_REGISTER:
        if _relaxed_auth_limits():
            return (60, 45)
        return (60, 25)
    if path == AUTH_PATH_LOGIN:
        if _relaxed_auth_limits():
            return (60, 90)
        return (60, 45)
    return None


REDIS_KEY_NS = "rl:v2"
# TTL > window so key survives the minute slice; Redis still expires old keys.
REDIS_KEY_TTL_SEC = 120

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


def is_strict_rate_path(path: str) -> bool:
    """Tighter 30/min bucket for macro news and portfolio entity APIs."""
    if path == "/api/macro/news":
        return True
    return path == "/api/entities" or path.startswith("/api/entities/")


async def enforce_rate_limits(
    *,
    client_ip: str,
    authorization_header: str | None,
    path: str,
    email_hint: str | None = None,
) -> bool:
    """
    Returns True if allowed, False if should return 429.

    Order: strict endpoint bucket (if applicable), then general ip or user bucket.
    """
    try:
        r = get_async_redis()
    except Exception as e:
        logger.warning("rate_limit: redis client failed (fail-open): %s", e)
        return True

    wid = _window_id()
    user_id = _bearer_user_id(authorization_header)
    ident = user_id or client_ip

    try:
        cfg = _auth_path_limits(path)
        if cfg is not None:
            window_sec, max_hits = cfg
            aw = int(time.time()) // max(1, window_sec)
            auth_key = f"{REDIS_KEY_NS}:auth:{path}:{client_ip}:{aw}"
            exceeded = await r.eval(
                _LUA_INCR_CHECK,
                1,
                auth_key,
                str(max_hits),
                str(max(REDIS_KEY_TTL_SEC, window_sec * 3)),
            )
            if int(exceeded):
                logger.warning(
                    "rate_limit_reject route=%s client_ip=%s email=%s limiter_key=%s reason=auth_window_exceeded max=%s window_s=%s",
                    path,
                    client_ip,
                    email_hint or "-",
                    auth_key,
                    max_hits,
                    window_sec,
                )
                return False
            return True

        if is_strict_rate_path(path):
            ep_key = f"{REDIS_KEY_NS}:endpoint:{path}:{ident}:{wid}"
            exceeded = await r.eval(
                _LUA_INCR_CHECK,
                1,
                ep_key,
                str(RATE_LIMIT_STRICT_PER_MINUTE),
                str(REDIS_KEY_TTL_SEC),
            )
            if int(exceeded):
                return False

        if user_id:
            user_key = f"{REDIS_KEY_NS}:user:{user_id}:{wid}"
            exceeded = await r.eval(
                _LUA_INCR_CHECK,
                1,
                user_key,
                str(RATE_LIMIT_USER_PER_MINUTE),
                str(REDIS_KEY_TTL_SEC),
            )
        else:
            ip_key = f"{REDIS_KEY_NS}:ip:{client_ip}:{wid}"
            exceeded = await r.eval(
                _LUA_INCR_CHECK,
                1,
                ip_key,
                str(RATE_LIMIT_IP_PER_MINUTE),
                str(REDIS_KEY_TTL_SEC),
            )
        if int(exceeded):
            return False
    except Exception as e:
        logger.warning("rate_limit: redis op failed (fail-open): %s", e)
        return True

    return True
