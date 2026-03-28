"""
Redis-backed HTTP response cache for GET /api/* (ASGI).

- Cache hit: skip route handler, log latency.
- Miss + lock holder: run app (buffered), store JSON 200 responses, coalesce concurrent misses.
- 5xx from origin: serve last stale body when available (external/upstream failure UI fallback).
- Logs: cache hit/miss, origin duration_ms; Redis counters stats:cache_hits, stats:cache_misses, stats:cache_origin_runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.redis_async import get_async_redis

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "resp:v1:"
STALE_KEY_PREFIX = "resp:stale:v1:"
LOCK_KEY_PREFIX = "resp:lock:v1:"

# Skip caching (auth flows, non-data).
SKIP_PATH_PREFIXES: tuple[str, ...] = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
)

# Per-user CRUD reads must not be served from Redis after POST/PATCH/DELETE; cache invalidation is not wired.
BYPASS_CACHE_PATH_PREFIXES: tuple[str, ...] = (
    "/api/auth/",
    "/api/portfolios",
    "/api/entities/",
    "/api/research/folders",
    "/api/research/projects",
    "/api/schedules",
    "/api/alerts",
    "/api/keyword-groups",
    "/api/groups",
    "/api/reports",
)

BODY_MAX_BYTES = 6 * 1024 * 1024
WAIT_ITERATIONS = 90
WAIT_SEC = 0.05
LOCK_TTL_SEC = 50


def _ttl_stale_for_path(path: str) -> tuple[int, int]:
    """Returns (ttl_seconds, stale_retention_seconds)."""
    if path.startswith("/api/market/"):
        return 600, 172800  # 10m hot, 48h stale fallback
    if path.startswith("/api/macro/news"):
        return 900, 172800  # 15m
    if path.startswith("/api/macro/"):
        return 900, 172800
    if "/metrics/search-trend" in path or path.endswith("/trending"):
        return 43_200, 172800  # 12h (trends)
    return 180, 86_400  # default 3m / 24h stale


def _cache_key(scope: Scope) -> tuple[str, str, str]:
    path = scope.get("path") or ""
    qs = scope.get("query_string", b"").decode("latin-1", errors="replace")
    headers = list(scope.get("headers") or [])
    hdr = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in headers}
    auth = hdr.get("authorization") or ""
    raw = f"{path}?{qs}|{auth}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest, path, qs


def _flatten_messages(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
    if not messages:
        return {"type": "http.response.start", "status": 500, "headers": []}, b""
    start = messages[0]
    if start.get("type") != "http.response.start":
        return {"type": "http.response.start", "status": 500, "headers": []}, b""
    parts: list[bytes] = []
    for m in messages[1:]:
        if m.get("type") == "http.response.body":
            parts.append(m.get("body") or b"")
    return start, b"".join(parts)


def _headers_dict(header_list: list[tuple[bytes, bytes]]) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in header_list}


def _pick_extra_headers(full: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for hk in ("x-macro-news-source", "x-macro-news-stale"):
        if hk in full:
            out[hk] = full[hk]
    return out


async def _send_flat_response(send: Send, start_msg: dict[str, Any], body: bytes, extra_headers: list[tuple[bytes, bytes]]) -> None:
    base_headers = list(start_msg.get("headers") or [])
    filtered: list[tuple[bytes, bytes]] = []
    for k, v in base_headers:
        if k.lower() == b"content-length":
            continue
        filtered.append((k, v))
    for k, v in extra_headers:
        filtered.append((k, v))
    filtered.append((b"content-length", str(len(body)).encode("ascii")))
    await send(
        {
            "type": "http.response.start",
            "status": int(start_msg.get("status", 200)),
            "headers": filtered,
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _send_json_pack(send: Send, pack: dict[str, Any], *, cache_status: bytes, stale: bool) -> None:
    body_str = pack["body"]
    if not isinstance(body_str, str):
        body_str = json.dumps(body_str)
    body = body_str.encode("utf-8")
    extra = pack.get("headers") or {}
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"x-cache", cache_status),
    ]
    if stale:
        headers.append((b"x-cache-stale", b"true"))
    for hk, hv in extra.items():
        headers.append((hk.lower().encode("latin-1"), str(hv).encode("latin-1")))
    await send({"type": "http.response.start", "status": int(pack.get("status", 200)), "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


class ResponseCacheMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        if any(path.startswith(p) for p in SKIP_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        if any(path.startswith(p) for p in BYPASS_CACHE_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        digest, path_s, _qs = _cache_key(scope)
        rkey = CACHE_KEY_PREFIX + digest
        stale_key = STALE_KEY_PREFIX + digest
        lock_key = LOCK_KEY_PREFIX + digest

        t0 = time.perf_counter()
        try:
            r = get_async_redis()
            cached = await r.get(rkey)
        except Exception as e:
            logger.warning("response_cache: redis get failed (bypass): %s", e)
            await self.app(scope, receive, send)
            return

        if cached:
            try:
                pack = json.loads(cached)
                dt_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "response_cache HIT path=%s key=%s duration_ms=%.1f",
                    path_s,
                    digest[:12],
                    dt_ms,
                )
                try:
                    await r.incr("stats:cache_hits")
                except Exception:
                    pass
                try:
                    from app.services.core_data_diag import record_cache_hit_layer

                    record_cache_hit_layer("redis_http")
                except Exception:
                    pass
                await _send_json_pack(send, pack, cache_status=b"HIT", stale=False)
            except Exception as e:
                logger.warning("response_cache: corrupted entry, bypass: %s", e)
                await self.app(scope, receive, send)
            return

        try:
            r = get_async_redis()
            got_lock = await r.set(lock_key, "1", nx=True, ex=LOCK_TTL_SEC) is True
        except Exception as e:
            logger.warning("response_cache lock redis error (bypass cache): %s", e)
            await self.app(scope, receive, send)
            return

        if not got_lock:
            for _ in range(WAIT_ITERATIONS):
                await asyncio.sleep(WAIT_SEC)
                try:
                    r = get_async_redis()
                    peer = await r.get(rkey)
                except Exception:
                    peer = None
                if peer:
                    try:
                        pack = json.loads(peer)
                        logger.info("response_cache HIT_AFTER_WAIT path=%s key=%s", path_s, digest[:12])
                        try:
                            await r.incr("stats:cache_hits")
                        except Exception:
                            pass
                        try:
                            from app.services.core_data_diag import record_cache_hit_layer

                            record_cache_hit_layer("redis_http")
                        except Exception:
                            pass
                        await _send_json_pack(send, pack, cache_status=b"HIT", stale=False)
                        return
                    except Exception:
                        break
            try:
                r = get_async_redis()
                got_lock = await r.set(lock_key, "1", nx=True, ex=LOCK_TTL_SEC) is True
            except Exception as e:
                logger.warning("response_cache lock retry failed (origin without lock): %s", e)
                await self._run_origin_buffer_store(scope, receive, send, path_s, rkey, stale_key, t0)
                return
            if not got_lock:
                await self._run_origin_buffer_store(scope, receive, send, path_s, rkey, stale_key, t0)
                return

        try:
            await self._run_origin_buffer_store(scope, receive, send, path_s, rkey, stale_key, t0)
        finally:
            if got_lock:
                try:
                    await get_async_redis().delete(lock_key)
                except Exception:
                    pass

    async def _run_origin_buffer_store(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        path_s: str,
        rkey: str,
        stale_key: str,
        t0: float,
    ) -> None:
        messages: list[dict[str, Any]] = []

        async def buffering_send(message: dict[str, Any]) -> None:
            messages.append(message)

        try:
            await self.app(scope, receive, buffering_send)
        except Exception:
            logger.exception("response_cache: app raised")
            try:
                r = get_async_redis()
                stale_raw = await r.get(stale_key)
            except Exception:
                stale_raw = None
            if stale_raw:
                try:
                    pack = json.loads(stale_raw)
                    logger.warning("response_cache: exception, serving STALE path=%s", path_s)
                    await _send_json_pack(send, pack, cache_status=b"STALE", stale=True)
                    return
                except Exception:
                    pass
            raise

        start_msg, body = _flatten_messages(messages)
        status = int(start_msg.get("status", 0))
        hdr_map = _headers_dict(list(start_msg.get("headers") or []))
        duration_ms = (time.perf_counter() - t0) * 1000

        try:
            await get_async_redis().incr("stats:cache_misses")
            await get_async_redis().incr("stats:cache_origin_runs")
        except Exception:
            pass

        logger.info(
            "response_cache MISS path=%s status=%s bytes=%d origin_ms=%.1f",
            path_s,
            status,
            len(body),
            duration_ms,
        )
        try:
            from app.services.core_data_diag import record_slow_route

            record_slow_route(path_s, duration_ms)
        except Exception:
            pass

        if status >= 500:
            try:
                stale_raw = await get_async_redis().get(stale_key)
            except Exception:
                stale_raw = None
            if stale_raw:
                try:
                    pack = json.loads(stale_raw)
                    logger.warning("response_cache: 5xx serving STALE path=%s", path_s)
                    await _send_json_pack(send, pack, cache_status=b"STALE", stale=True)
                    return
                except Exception:
                    pass

        extra_send_headers: list[tuple[bytes, bytes]] = [(b"x-cache", b"MISS")]
        await _send_flat_response(send, start_msg, body, extra_send_headers)

        ttl, stale_ttl = _ttl_stale_for_path(path_s)
        if status == 200 and 0 < len(body) <= BODY_MAX_BYTES:
            ct = hdr_map.get("content-type", "")
            is_json = "application/json" in ct or body[:1] in (b"{", b"[")
            if is_json:
                try:
                    decoded = body.decode("utf-8")
                    body_json = json.loads(decoded)
                    if isinstance(body_json, dict):
                        ds = body_json.get("data_source")
                        ls = body_json.get("loading_state")
                        if ds == "placeholder" or ls in ("warming", "placeholder"):
                            ttl = min(int(ttl), 45)
                    skip_store = False
                    if (
                        path_s.startswith("/api/macro/news")
                        and isinstance(body_json, dict)
                        and body_json.get("data") == []
                        and body_json.get("loading_state") not in ("warming", "placeholder")
                    ):
                        skip_store = True
                    if (
                        path_s.startswith("/api/market/indices")
                        and isinstance(body_json, dict)
                        and isinstance(body_json.get("data"), list)
                        and len(body_json["data"]) == 0
                        and body_json.get("loading_state") != "placeholder"
                    ):
                        skip_store = True
                    if skip_store:
                        logger.debug("response_cache: skip store (empty body without explicit warming state)")
                    else:
                        pack = {
                            "status": status,
                            "headers": _pick_extra_headers(hdr_map),
                            "body": decoded,
                        }
                        payload = json.dumps(pack)
                        pipe = get_async_redis().pipeline()
                        pipe.setex(rkey, ttl, payload)
                        pipe.setex(stale_key, stale_ttl, payload)
                        await pipe.execute()
                except Exception as e:
                    logger.debug("response_cache: store skipped %s", e)
