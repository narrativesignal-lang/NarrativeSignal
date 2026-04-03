"""
Rolling background repair: Massive fills missing/stale quote + 1M OHLCV for tracked symbols only.

Cadence: Celery beat + Redis ``last_exec_wall_ts`` (off-hours 60m) + distributed run lock.
All Massive HTTP is via ``massive_api_client`` (quota inside that layer).
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.data_subscription import MarketQuoteSnapshot, OhlcvSnapshot
from app.services.market_snapshots import collect_symbols_for_scheduled_market_refresh
from app.services.massive_market_data_provider import (
    fetch_massive_ohlcv_batch,
    fetch_massive_quotes_batch,
    massive_enabled,
    write_massive_ohlcv_to_snapshots,
    write_massive_quotes_to_snapshots,
)

logger = logging.getLogger(__name__)

_NY = ZoneInfo("America/New_York")
_FRESH = timedelta(hours=1)
_MAX_REFRESH_PER_RUN = 10
_OFFHOURS_COOLDOWN_SEC = 3600.0
_LOCK_TTL_SEC = 900

_REDIS_CURSOR = "market:v1:massive_repair_scan:cursor"
_REDIS_LAST_RUN = "market:v1:massive_repair_scan:last_run_at"
_REDIS_LAST_FULL_CYCLE = "market:v1:massive_repair_scan:last_full_cycle_completed_at"
_REDIS_LAST_EXEC_TS = "market:v1:massive_repair_scan:last_exec_wall_ts"
_REDIS_RUN_LOCK = "market:v1:massive_repair_scan:run_lock"

_RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
)


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def acquire_massive_repair_scan_lock() -> tuple[bool, str | None]:
    """
    Distributed lock: only one repair scan across workers.
    Returns (acquired, token). Release with ``release_massive_repair_scan_lock(token)``.
    """
    token = str(uuid.uuid4())
    try:
        ok = bool(_r().set(_REDIS_RUN_LOCK, token, nx=True, ex=_LOCK_TTL_SEC))
        return (ok, token if ok else None)
    except Exception as e:
        logger.warning("massive_repair_scan lock_acquire_failed err=%s", str(e)[:120])
        return (False, None)


def release_massive_repair_scan_lock(token: str | None) -> None:
    if not token:
        return
    try:
        _r().eval(_RELEASE_LOCK_LUA, 1, _REDIS_RUN_LOCK, token)
    except Exception as e:
        logger.warning("massive_repair_scan lock_release_failed err=%s", str(e)[:120])


def repair_scan_offhours_cooldown_blocks_after_lock() -> str | None:
    """
    After lock is held: outside RTH, require >= 60 minutes since ``last_exec_wall_ts``.
    Does not rely on Celery beat spacing alone.
    Returns None if execution may proceed, else skip reason.
    """
    now = datetime.now(timezone.utc)
    if is_ny_weekday_regular_session(now):
        return None
    try:
        raw = _r().get(_REDIS_LAST_EXEC_TS)
        last = float(raw) if raw else 0.0
        if time.time() - last < _OFFHOURS_COOLDOWN_SEC:
            return "offhours_cooldown_after_lock_lt_3600s"
    except Exception as e:
        return f"offhours_cooldown_redis_error:{str(e)[:80]}"
    return None


def is_ny_weekday_regular_session(now_utc: datetime | None = None) -> bool:
    """Weekday 09:30–16:00 America/New_York. No exchange calendar in repo → weekday-only."""
    now = now_utc or datetime.now(timezone.utc)
    ny = now.astimezone(_NY)
    if ny.weekday() >= 5:
        return False
    t = ny.time()
    from datetime import time as dtime

    return dtime(9, 30) <= t < dtime(16, 0)


def repair_scan_should_execute_tick(*, now_utc: datetime | None = None) -> tuple[bool, str]:
    """
    Celery fires every 10m. During RTH, always allow. Off-hours, at most once per 60 minutes.
    Returns (allow, skip_reason_or_ok).
    """
    now = now_utc or datetime.now(timezone.utc)
    if is_ny_weekday_regular_session(now):
        return True, "ny_regular_session"
    try:
        client = _r()
        raw = client.get(_REDIS_LAST_EXEC_TS)
        last = float(raw) if raw else 0.0
        if time.time() - last < 3600.0:
            return False, "offhours_throttle_lt_3600s"
    except Exception as e:
        return False, f"offhours_throttle_redis_error:{str(e)[:80]}"
    return True, "offhours_due"


def _quote_stale_or_missing(db: Session, sym: str, now: datetime) -> bool:
    snap = db.get(MarketQuoteSnapshot, sym)
    if snap is None:
        return True
    if snap.last_success_at is None:
        return True
    return snap.last_success_at < now - _FRESH


def _ohlcv_stale_or_missing(db: Session, sym: str, now: datetime, period: str = "1M") -> bool:
    key = f"{sym}:{period}"
    snap = db.get(OhlcvSnapshot, key)
    if snap is None:
        return True
    if snap.last_success_at is None:
        return True
    bars = (snap.bars or {}).get("bars") if snap.bars else None
    if not bars:
        return True
    return snap.last_success_at < now - _FRESH


def _repair_one_symbol(db: Session, sym: str, now: datetime) -> tuple[str, bool]:
    """
    Returns (status, refreshed). Quota is enforced inside ``massive_api_client`` (via fetch_*).
    """
    need_q = _quote_stale_or_missing(db, sym, now)
    need_o = _ohlcv_stale_or_missing(db, sym, now)
    if not need_q and not need_o:
        return "skip_not_eligible", False

    refreshed = False
    if need_q:
        try:
            qmap, qstop = fetch_massive_quotes_batch([sym])
            if qstop == "massive_quota_per_minute":
                return "quota_minute", refreshed
            if qstop == "massive_quota_per_day":
                return "quota_day", refreshed
            if qstop == "massive_rate_limited":
                return "rate_limited", refreshed
            n = write_massive_quotes_to_snapshots(db, qmap)
            db.commit()
            if n > 0:
                refreshed = True
        except Exception as e:
            db.rollback()
            logger.warning("massive_repair_scan quote sym=%s err=%s", sym, str(e)[:200])
            return "failed", refreshed

    if need_o:
        try:
            omap, ostop = fetch_massive_ohlcv_batch([sym], period="1M")
            if ostop == "massive_quota_per_minute":
                return "quota_minute", refreshed
            if ostop == "massive_quota_per_day":
                return "quota_day", refreshed
            if ostop == "massive_rate_limited":
                return "rate_limited", refreshed
            n = write_massive_ohlcv_to_snapshots(db, omap, period="1M")
            db.commit()
            if n > 0:
                refreshed = True
        except Exception as e:
            db.rollback()
            logger.warning("massive_repair_scan ohlcv sym=%s err=%s", sym, str(e)[:200])
            return "failed", refreshed

    return "ok", refreshed


def run_massive_market_repair_scan(db: Session) -> dict:
    """
    One scan pass: walk tracked symbols from Redis cursor, max 10 refreshes, max one full list inspection.
    """
    t0 = time.perf_counter()
    now = datetime.now(timezone.utc)

    if not massive_enabled():
        return {"skipped": True, "reason": "massive_not_configured", "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)}

    symbols = sorted(collect_symbols_for_scheduled_market_refresh(db))
    tracked_count = len(symbols)
    cursor_position_before = 0
    cursor_position_after = 0
    wrapped_around = False

    if tracked_count == 0:
        logger.info(
            "job=massive_repair_scan run_started tracked_count=0 run_finished=1 inspected_count=0 "
            "items_refreshed=0 cursor_position_before=0 cursor_position_after=0"
        )
        return {
            "tracked_count": 0,
            "inspected_count": 0,
            "items_refreshed": 0,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    try:
        client = _r()
        raw_c = client.get(_REDIS_CURSOR)
        c = int(raw_c) if raw_c is not None and str(raw_c).isdigit() else 0
        if c < 0 or c >= tracked_count:
            c = 0
        cursor_position_before = c
    except Exception:
        c = 0
        cursor_position_before = 0

    start = c % tracked_count
    inspected_count = 0
    items_refreshed = 0
    items_attempted = 0
    items_failed = 0
    candidates_found = 0
    skipped_due_to_per_minute_limit = 0
    skipped_due_to_per_day_limit = 0
    pos = start

    logger.info(
        "job=massive_repair_scan run_started tracked_count=%s cursor_position_before=%s",
        tracked_count,
        cursor_position_before,
    )

    while inspected_count < tracked_count and items_refreshed < _MAX_REFRESH_PER_RUN:
        sym = symbols[pos]
        need_any = _quote_stale_or_missing(db, sym, now) or _ohlcv_stale_or_missing(db, sym, now)
        if need_any:
            candidates_found += 1
            items_attempted += 1
            status, did_refresh = _repair_one_symbol(db, sym, now)
            if status == "quota_minute":
                skipped_due_to_per_minute_limit = 1
                inspected_count += 1
                pos = (pos + 1) % tracked_count
                break
            if status == "quota_day":
                skipped_due_to_per_day_limit = 1
                inspected_count += 1
                pos = (pos + 1) % tracked_count
                break
            if status == "rate_limited":
                inspected_count += 1
                pos = (pos + 1) % tracked_count
                break
            if status == "failed":
                items_failed += 1
            if did_refresh:
                items_refreshed += 1

        inspected_count += 1
        pos = (pos + 1) % tracked_count

    cursor_position_after = pos % tracked_count
    full_cycle = inspected_count >= tracked_count
    wrapped_around = full_cycle and tracked_count > 0

    try:
        client = _r()
        client.set(_REDIS_CURSOR, str(cursor_position_after))
        client.set(_REDIS_LAST_RUN, now.isoformat())
        client.set(_REDIS_LAST_EXEC_TS, str(time.time()))
        if full_cycle:
            client.set(_REDIS_LAST_FULL_CYCLE, now.isoformat())
    except Exception as e:
        logger.warning("massive_repair_scan redis_persist_failed err=%s", str(e)[:120])

    elapsed = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=massive_repair_scan run_finished tracked_count=%s candidates_found=%s items_attempted=%s "
        "items_refreshed=%s items_failed=%s inspected_count=%s cursor_position_before=%s "
        "cursor_position_after=%s wrapped_around=%s skipped_due_to_per_minute_limit=%s "
        "skipped_due_to_per_day_limit=%s elapsed_ms=%s full_cycle=%s",
        tracked_count,
        candidates_found,
        items_attempted,
        items_refreshed,
        items_failed,
        inspected_count,
        cursor_position_before,
        cursor_position_after,
        1 if wrapped_around else 0,
        skipped_due_to_per_minute_limit,
        skipped_due_to_per_day_limit,
        elapsed,
        1 if full_cycle else 0,
    )

    return {
        "tracked_count": tracked_count,
        "candidates_found": candidates_found,
        "items_attempted": items_attempted,
        "items_refreshed": items_refreshed,
        "items_failed": items_failed,
        "inspected_count": inspected_count,
        "cursor_position_before": cursor_position_before,
        "cursor_position_after": cursor_position_after,
        "wrapped_around": wrapped_around,
        "skipped_due_to_per_minute_limit": bool(skipped_due_to_per_minute_limit),
        "skipped_due_to_per_day_limit": bool(skipped_due_to_per_day_limit),
        "full_cycle": full_cycle,
        "elapsed_ms": elapsed,
    }
