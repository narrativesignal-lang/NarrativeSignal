"""Shared Yahoo/yfinance pacing and rate-limit cooldown (Redis) for Celery + API refresh paths."""

from __future__ import annotations

import logging
import time

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_PAUSE_UNTIL_KEY = "market:v1:yahoo_pause_until_ts"
_LAST_CALL_KEY = "market:v1:yahoo_last_fetch_ts"


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def yahoo_provider_paused() -> bool:
    """True if we recently hit a Yahoo rate limit and should skip new yfinance calls."""
    try:
        raw = _r().get(_PAUSE_UNTIL_KEY)
        if not raw:
            return False
        return time.time() < float(raw)
    except Exception:
        return False


def yahoo_pause(*, seconds: int | None = None) -> None:
    """Pause yahoo fallback until now + seconds (also sets TTL on key). Minimum 10 minutes after rate limits."""
    configured = int(getattr(settings, "yahoo_rate_limit_cooldown_seconds", 600) or 600)
    sec = seconds if seconds is not None else configured
    # Hard floor: avoid hammering Yahoo after YFRateLimitError / 429 storms.
    sec = max(600, int(sec))
    until = time.time() + sec
    try:
        _r().setex(_PAUSE_UNTIL_KEY, sec + 120, str(until))
    except Exception as e:
        logger.debug("yahoo_pause redis failed: %s", e)
    logger.warning("market_yahoo_guard action=pause_until seconds=%s until_ts=%.0f", sec, until)


def yahoo_spacing_sleep_before_call() -> None:
    """Minimum spacing between yfinance outbound calls (per-process cluster via Redis)."""
    interval = float(getattr(settings, "yahoo_fallback_min_interval_seconds", 1.25) or 1.25)
    interval = max(0.2, interval)
    try:
        r = _r()
        raw = r.get(_LAST_CALL_KEY)
        now = time.time()
        if raw:
            elapsed = now - float(raw)
            if elapsed < interval:
                time.sleep(interval - elapsed)
        r.setex(_LAST_CALL_KEY, 180, str(time.time()))
    except Exception:
        time.sleep(interval)


def yahoo_mark_rate_limited() -> None:
    """Call when yfinance signals Too Many Requests / rate limit."""
    yahoo_pause()


def exception_looks_like_yahoo_rate_limit(exc: BaseException) -> bool:
    msg = (str(exc) or "").lower()
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        return True
    if "too many requests" in msg or "429" in msg or "rate limit" in msg or "temporarily unavailable" in msg:
        return True
    return False
