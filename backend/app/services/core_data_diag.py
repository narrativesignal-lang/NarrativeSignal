"""Counters and logs for core-data path (snapshots, warmup, fallbacks, cold external)."""

from __future__ import annotations

import logging
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def bump(stat: str, n: int = 1) -> None:
    if n <= 0:
        return
    try:
        _client().incrby(f"stats:core:{stat}", n)
    except Exception as e:
        logger.debug("core_data_diag bump %s: %s", stat, e)


def record_snapshot_hit(api_tag: str) -> None:
    bump(f"snapshot_hit:{api_tag}")
    logger.debug("core_data snapshot_hit %s", api_tag)


def record_cache_hit_layer(layer: str) -> None:
    bump(f"layer_hit:{layer}")


def record_fallback(tag: str) -> None:
    bump("fallback_total")
    bump(f"fallback:{tag}")
    logger.info("core_data fallback %s", tag)


def record_cold_external(tag: str) -> None:
    bump("cold_external_total")
    bump(f"cold_external:{tag}")
    logger.warning("core_data cold_external_sync %s", tag)


def record_warmup(ok: bool) -> None:
    bump("warmup_runs")
    bump("warmup_ok" if ok else "warmup_fail")
    logger.info("core_data warmup outcome=%s", "ok" if ok else "fail")


def record_first_paint_envelope(path_key: str, *, loading_state: str | None, data_source: str | None) -> None:
    """Diagnostic: how often first-screen responses use fallbacks (Redis counters)."""
    ls = (loading_state or "").strip().lower()
    ds = (data_source or "").strip().lower()
    if ls == "placeholder":
        bump(f"fp:placeholder:{path_key}")
    if ls == "warming":
        bump(f"fp:warming:{path_key}")
    if ds == "stale_fallback":
        bump(f"fp:stale_fallback:{path_key}")
    if ds == "placeholder":
        bump(f"fp:ds_placeholder:{path_key}")
    logger.debug("first_paint path=%s loading_state=%s data_source=%s", path_key, ls or "-", ds or "-")


def record_cold_empty(path_key: str) -> None:
    bump(f"cold_empty:{path_key}")
    logger.info("first_paint cold_empty path=%s", path_key)


def record_slow_route(path: str, ms: float) -> None:
    if ms < 1500:
        return
    try:
        c = _client()
        key = "stats:core:slow_routes"
        c.zadd(key, {path[:200]: ms})
        c.zremrangebyrank(key, 0, -51)
    except Exception:
        pass


def get_core_diag_snapshot() -> dict[str, Any]:
    """Admin/debug: pull aggregate counters from Redis."""
    out: dict[str, Any] = {"slow_routes": []}
    try:
        c = _client()
        prefix = "stats:core:"
        for raw in c.scan_iter(f"{prefix}*", count=50):
            k = str(raw)
            if k.endswith(":slow_routes"):
                continue
            try:
                out[k.replace(prefix, "")] = c.get(k)
            except Exception:
                out[k] = None
        z = c.zrevrange("stats:core:slow_routes", 0, 14, withscores=True)
        out["slow_routes"] = [{"path": p, "ms": float(s)} for p, s in z]
    except Exception as e:
        out["error"] = str(e)
    return out
