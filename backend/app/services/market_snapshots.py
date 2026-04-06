"""Persisted market quotes and OHLCV: refresh with fallback (never null-out successful values)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.data_subscription import MarketQuoteSnapshot, OhlcvSnapshot, UserDataSubscription
from app.services.cache_fallback import merge_quote_row, utcnow
from app.services.market.service import (
    fetch_batch_ohlcv_yahoo,
    fetch_batch_quotes_yahoo,
    fetch_quote_stooq,
    fetch_quote_yahoo,
    get_ohlcv,
)
from app.services.market.yahoo_guard import yahoo_provider_paused
from app.services.market_provider_router import route_quote_provider
from app.services.symbol_mapping import map_symbol_for_twelve, normalize_user_symbol
from app.services.twelve_data_service import get_quote as twelve_get_quote
from app.services.twelve_data_service import get_quotes_batch as twelve_get_quotes_batch
from app.services.twelve_data_service import get_time_series as twelve_get_time_series
from app.services.twelve_data_service import is_twelve_configured
from app.services.twelve_data_service import twelve_rate_limited_recent
from app.services.twelve_symbol_support import is_twelve_supported_symbol
from app.services.twelve_warm_pool import TWELVE_WARM_1M_INTERVAL
from app.services.runtime_flags import RuntimeFlagKey, provider_enabled

logger = logging.getLogger(__name__)

# Keep in sync with api/routes/market.py PERIOD_TO_TWELVE
PERIOD_TO_TWELVE_FETCH: dict[str, tuple[str, int]] = {
    "1D": ("1day", 14),
    "5D": ("1day", 10),
    "1M": ("1day", 40),
    "6M": ("1day", 200),
    "1Y": ("1day", 400),
    "MAX": ("1week", 520),
}

QUOTE_LAST_GOOD_PREFIX = "market:quote:last_good:v1:"
QUOTE_LAST_GOOD_TTL_SEC = 86400 * 14

# Batch sizing defaults (request-count control knobs)
QUOTE_BATCH_CHUNK_SIZE = 20
OHLCV_BATCH_CHUNK_SIZE = 20


def _now_iso() -> str:
    return utcnow().isoformat()


def refresh_quotes_batch_with_fallback(
    db: Session,
    symbols: list[str],
    *,
    max_chunks_per_run: int = 5,
) -> dict:
    """
    Batch quote refresh for symbols: Twelve(batch) -> Yahoo(batch) -> fallback_provider(batch adapter).
    Writes MarketQuoteSnapshot rows only (no provider calls in HTTP handlers).
    """
    from app.services.chunking import chunk_symbols

    syms = [(s or "").strip().upper() for s in (symbols or []) if (s or "").strip()]
    batches = chunk_symbols(syms, QUOTE_BATCH_CHUNK_SIZE)
    if max_chunks_per_run > 0:
        batches = batches[: int(max_chunks_per_run)]
    request_count = 0
    fallback_count = 0
    success = 0
    fail = 0

    for chunk in batches:
        twelve_quotes_enabled = provider_enabled(db, RuntimeFlagKey.ENABLE_TWELVE_QUOTES)
        yahoo_quotes_enabled = provider_enabled(db, RuntimeFlagKey.ENABLE_YAHOO_QUOTES)
        stooq_enabled = provider_enabled(db, RuntimeFlagKey.ENABLE_STOOQ_FALLBACK)

        # Stage 1: Twelve batch for mappable
        mappable: dict[str, str] = {}
        for s in chunk:
            norm = normalize_user_symbol(s)
            if twelve_quotes_enabled and is_twelve_configured() and map_symbol_for_twelve(norm) is not None:
                td_sym = map_symbol_for_twelve(norm)
                if td_sym:
                    mappable[s] = td_sym

        twelve_hit: dict[str, dict | None] = {}
        if mappable:
            request_count += 1
            td_payload = twelve_get_quotes_batch(list(mappable.values()))
            # map back to original chunk symbols
            for orig, mapped in mappable.items():
                twelve_hit[orig] = td_payload.get(mapped) if td_payload else None

        missing = [s for s in chunk if not (twelve_hit.get(s) and twelve_hit[s].get("price") is not None)]
        if missing:
            fallback_count += len(missing)

        # Stage 2: Yahoo batch for remaining
        yahoo_rows: dict[str, dict] = {}
        twelve_cooling = bool(missing and twelve_rate_limited_recent())
        if missing and yahoo_quotes_enabled and not twelve_cooling:
            request_count += 1
            yahoo_rows = fetch_batch_quotes_yahoo(missing)
        elif missing and twelve_cooling:
            logger.info(
                "refresh_quotes_batch_with_fallback yahoo skipped due to recent twelve local rate limit chunk_size=%s",
                len(missing),
            )

        missing2 = [s for s in missing if not (yahoo_rows.get(s) and yahoo_rows[s].get("price") is not None)]
        if missing2:
            fallback_count += len(missing2)

        # Stage 3: fallback_provider batch adapter (currently stooq per-symbol inside adapter)
        fb_rows: dict[str, dict] = {}
        if missing2 and stooq_enabled:
            request_count += 1
            for s in missing2:
                fb_rows[s] = fetch_quote_stooq(s)

        attempt = utcnow()
        for s in chunk:
            snap = db.get(MarketQuoteSnapshot, s)
            if snap is None:
                snap = MarketQuoteSnapshot(symbol=s)
                db.add(snap)
            prev_p = snap.price
            prev_c = snap.change_percent

            provider_selected = "none"
            new_p = None
            new_c = None
            err: str | None = None

            td = twelve_hit.get(s)
            if td and td.get("price") is not None:
                provider_selected = "twelve"
                new_p = round(float(td["price"]), 2)
                pct = td.get("percent_change")
                new_c = round(float(pct), 2) if pct is not None else None
                err = None
            else:
                y = yahoo_rows.get(s) or {}
                if y.get("price") is not None:
                    provider_selected = "yahoo"
                    new_p = round(float(y["price"]), 2)
                    pct = y.get("change_percent")
                    new_c = round(float(pct), 2) if pct is not None else None
                    err = None
                else:
                    fb = fb_rows.get(s) or {}
                    if fb.get("price") is not None:
                        provider_selected = "fallback_provider"
                        new_p = round(float(fb["price"]), 2)
                        pct = fb.get("change_percent")
                        new_c = round(float(pct), 2) if pct is not None else None
                        err = None
                    else:
                        err = "unavailable_all_providers"

            merged_p, merged_c = merge_quote_row(prev_p, prev_c, new_p, new_c)
            snap.price = merged_p
            snap.change_percent = merged_c
            snap.last_attempt_at = attempt
            snap.provider_source = provider_selected if provider_selected != "none" else (snap.provider_source or None)
            live_ok = new_p is not None and err is None
            if live_ok:
                snap.last_success_at = attempt
                snap.last_error = None
                snap.is_stale = False
                success += 1
            else:
                snap.last_error = err or (snap.last_error if snap.last_error else None)
                snap.is_stale = bool(prev_p is not None and new_p is None)
                fail += 1

            if merged_p is not None:
                try:
                    ts = (snap.last_success_at or attempt).isoformat()
                    cache_last_good_quote(s, float(merged_p), merged_c, updated_at_iso=ts)
                except Exception:
                    pass

    return {
        "symbol_count": len(syms),
        "chunk_count": len(batches),
        "chunk_size": QUOTE_BATCH_CHUNK_SIZE,
        "request_count": request_count,
        "fallback_count": fallback_count,
        "success_count": success,
        "fail_count": fail,
    }


def refresh_ohlcv_batch_with_fallback(db: Session, symbols: list[str], *, periods: tuple[str, ...]) -> dict:
    """
    Batch OHLCV refresh (snapshot table only). To control request counts:
    - Yahoo uses true batch download per chunk
    - Twelve stage uses a batch-shaped adapter (chunk-local loop; business still sees batch)
    - fallback_provider stage uses per-symbol adapter internally
    """
    from app.services.chunking import chunk_symbols
    from app.services.twelve_data_service import get_time_series_batch as twelve_get_time_series_batch

    syms = [(s or "").strip().upper() for s in (symbols or []) if (s or "").strip()]
    batches = chunk_symbols(syms, OHLCV_BATCH_CHUNK_SIZE)
    request_count = 0
    fallback_count = 0
    success_cells = 0
    fail_cells = 0

    for p in periods:
        for chunk in batches:
            twelve_enabled = provider_enabled(db, RuntimeFlagKey.ENABLE_TWELVE_OHLCV)
            yahoo_enabled = provider_enabled(db, RuntimeFlagKey.ENABLE_YAHOO_OHLCV)
            stooq_enabled = provider_enabled(db, RuntimeFlagKey.ENABLE_STOOQ_FALLBACK)

            twelve_map: dict[str, list[dict]] = {s: [] for s in chunk}
            yahoo_map: dict[str, list] = {s: [] for s in chunk}
            fb_map: dict[str, list] = {}

            # Stage 1: Twelve time_series (batch-shaped; per-symbol within chunk)
            if twelve_enabled and is_twelve_configured() and p in PERIOD_TO_TWELVE_FETCH:
                iv, osz = PERIOD_TO_TWELVE_FETCH[p]
                provider_stage = "twelve"
                try:
                    # Count per-symbol external requests (adapter loops).
                    request_count += len(chunk)
                    raw_map = twelve_get_time_series_batch(chunk, interval=iv, outputsize=osz)
                    for s in chunk:
                        raw = raw_map.get(s) or []
                        if raw:
                            twelve_map[s] = [_bar_from_twelve_dict(b) for b in raw if isinstance(b, dict) and b.get("time")]
                    logger.info(
                        "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s request_count=%s fallback_count=%s",
                        provider_stage,
                        p,
                        len(chunk),
                        request_count,
                        fallback_count,
                    )
                except Exception as e:
                    logger.warning(
                        "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s err=%s request_count=%s fallback_count=%s",
                        provider_stage,
                        p,
                        len(chunk),
                        str(e)[:200],
                        request_count,
                        fallback_count,
                    )
            else:
                provider_stage = "twelve_skipped"
                logger.info(
                    "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s request_count=%s fallback_count=%s",
                    provider_stage,
                    p,
                    len(chunk),
                    request_count,
                    fallback_count,
                )

            missing_after_twelve = [s for s in chunk if not twelve_map.get(s)]

            # Stage 2: Yahoo (true batch)
            provider_stage = "yahoo"
            twelve_cooling = bool(missing_after_twelve and twelve_rate_limited_recent())
            if yahoo_enabled and missing_after_twelve and not twelve_cooling:
                try:
                    request_count += 1
                    yahoo_map = fetch_batch_ohlcv_yahoo(missing_after_twelve, period=p)
                    logger.info(
                        "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s request_count=%s fallback_count=%s",
                        provider_stage,
                        p,
                        len(missing_after_twelve),
                        request_count,
                        fallback_count,
                    )
                except Exception as e:
                    logger.warning(
                        "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s err=%s request_count=%s fallback_count=%s",
                        provider_stage,
                        p,
                        len(missing_after_twelve),
                        str(e)[:200],
                        request_count,
                        fallback_count,
                    )
                    yahoo_map = {s: [] for s in missing_after_twelve}
            elif missing_after_twelve and twelve_cooling:
                logger.info(
                    "job=refresh_ohlcv_batch_with_fallback provider_stage=yahoo_skipped_recent_twelve_limit period=%s chunk_size=%s request_count=%s fallback_count=%s",
                    p,
                    len(missing_after_twelve),
                    request_count,
                    fallback_count,
                )
            elif missing_after_twelve:
                logger.info(
                    "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s skipped=1 request_count=%s fallback_count=%s",
                    "yahoo_skipped",
                    p,
                    len(missing_after_twelve),
                    request_count,
                    fallback_count,
                )

            missing_after_yahoo = [
                s for s in chunk if (not twelve_map.get(s)) and (not (yahoo_map or {}).get(s))
            ]

            # Stage 3: fallback_provider (stooq adapter, per-symbol)
            provider_stage = "fallback_provider"
            if missing_after_yahoo:
                fallback_count += len(missing_after_yahoo)
                if stooq_enabled:
                    # Count per-symbol adapter requests for visibility (stooq is per-symbol).
                    request_count += len(missing_after_yahoo)
                    for s in missing_after_yahoo:
                        try:
                            bars, _src = get_ohlcv(symbol=s, period=p)
                            fb_map[s] = bars
                        except Exception:
                            fb_map[s] = []
                    logger.info(
                        "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s request_count=%s fallback_count=%s",
                        provider_stage,
                        p,
                        len(missing_after_yahoo),
                        request_count,
                        fallback_count,
                    )
                else:
                    logger.info(
                        "job=refresh_ohlcv_batch_with_fallback provider_stage=%s period=%s chunk_size=%s skipped=1 request_count=%s fallback_count=%s",
                        "fallback_provider_skipped",
                        p,
                        len(missing_after_yahoo),
                        request_count,
                        fallback_count,
                    )

            attempt = utcnow()
            for s in chunk:
                key = f"{s}:{p}"
                snap = db.get(OhlcvSnapshot, key)
                if snap is None:
                    snap = OhlcvSnapshot(snapshot_key=key, symbol=s, period=p)
                    db.add(snap)

                bars = twelve_map.get(s) or (yahoo_map.get(s) if isinstance(yahoo_map, dict) else None) or fb_map.get(s) or []
                if bars:
                    snap.bars = {"bars": [_bar_to_dict(b) for b in bars]}
                    snap.last_success_at = attempt
                    snap.last_error = None
                    snap.is_stale = False
                    if twelve_map.get(s):
                        snap.provider_source = "twelve"
                    elif isinstance(yahoo_map, dict) and yahoo_map.get(s):
                        snap.provider_source = "yahoo"
                    elif fb_map.get(s):
                        snap.provider_source = "fallback_provider"
                    else:
                        snap.provider_source = snap.provider_source or None
                    success_cells += 1
                else:
                    snap.last_error = snap.last_error or "unavailable_all_providers"
                    snap.is_stale = True
                    fail_cells += 1
                snap.last_attempt_at = attempt

    return {
        "symbol_count": len(syms),
        "chunk_count": len(batches),
        "chunk_size": OHLCV_BATCH_CHUNK_SIZE,
        "request_count": request_count,
        "fallback_count": fallback_count,
        "success_count": success_cells,
        "fail_count": fail_cells,
        "periods": list(periods),
    }


def _with_backoff(fn, *, retries: int = 2, base_sleep_sec: float = 0.35):
    import time

    last_err: Exception | None = None
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if i >= retries:
                raise
            time.sleep(base_sleep_sec * (2**i))
    if last_err:
        raise last_err
    return None


def _quote_row_has_usable_snapshot(snap: MarketQuoteSnapshot | None) -> bool:
    """True if we can hold stale snapshot while Yahoo is in cooldown."""
    if snap is None:
        return False
    return snap.price is not None


def _quotes_r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def cache_last_good_quote(
    symbol: str,
    price: float,
    change_percent: float | None,
    *,
    updated_at_iso: str,
) -> None:
    sym = (symbol or "").strip().upper()
    if not sym or price is None:
        return
    try:
        payload = json.dumps(
            {"price": float(price), "change_percent": change_percent, "updated_at": updated_at_iso},
            default=str,
        )
        _quotes_r().setex(QUOTE_LAST_GOOD_PREFIX + sym, QUOTE_LAST_GOOD_TTL_SEC, payload)
    except Exception as e:
        logger.debug("cache_last_good_quote %s: %s", sym, e)


def load_last_good_quote(symbol: str) -> dict | None:
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    try:
        raw = _quotes_r().get(QUOTE_LAST_GOOD_PREFIX + sym)
        if not raw:
            return None
        o = json.loads(raw)
        if not isinstance(o, dict) or o.get("price") is None:
            return None
        return {
            "price": float(o["price"]),
            "change_percent": float(o["change_percent"]) if o.get("change_percent") is not None else None,
            "updated_at_iso": str(o.get("updated_at") or ""),
        }
    except Exception as e:
        logger.debug("load_last_good_quote %s: %s", sym, e)
        return None


def collect_symbols_for_scheduled_market_refresh(db: Session) -> set[str]:
    """
    Symbols to refresh on Celery: V1 core + default macro indices + active market_quote targets.
    """
    from app.services.market_indices_config import core_and_default_symbols

    syms = core_and_default_symbols()
    for tid in db.scalars(
        select(UserDataSubscription.target_id).where(
            UserDataSubscription.source_type == "market_quote",
            UserDataSubscription.is_active.is_(True),
        )
    ).all():
        t = str(tid).strip().upper()
        if t:
            syms.add(t)
    return syms


def _bar_from_twelve_dict(bar: dict) -> dict:
    """Twelve time_series row → OhlcvSnapshot bar shape (unix time), aligned with /market/time_series."""
    t_iso = str(bar.get("time") or "")
    unix = 0
    try:
        if t_iso.endswith("Z"):
            dt = datetime.fromisoformat(t_iso.replace("Z", "+00:00"))
        elif len(t_iso) == 10 and t_iso.count("-") == 2:
            dt = datetime.fromisoformat(t_iso + "T00:00:00+00:00")
        else:
            dt = datetime.fromisoformat(t_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        unix = int(dt.timestamp())
    except Exception:
        unix = 0
    vol = bar.get("volume")
    try:
        vi = int(vol) if vol is not None and float(vol) == int(float(vol)) else round(float(vol or 0), 0)
    except (TypeError, ValueError):
        vi = 0
    return {
        "time": unix,
        "open": round(float(bar.get("open") or 0), 4),
        "high": round(float(bar.get("high") or 0), 4),
        "low": round(float(bar.get("low") or 0), 4),
        "close": round(float(bar.get("close") or 0), 4),
        "volume": vi,
    }


def upsert_quote_twelve_warm(db: Session, symbol: str) -> str:
    """
    Warm quote: calls twelve_get_quote (fills Redis cache), merges into MarketQuoteSnapshot.
    Returns ok | skip | fail (fail = no new price from Twelve; prior snapshot preserved).
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return "fail"
    if not is_twelve_supported_symbol(sym):
        return "skip"
    snap = db.get(MarketQuoteSnapshot, sym)
    attempt = utcnow()
    err: str | None = None
    new_p: float | None = None
    new_c: float | None = None
    try:
        td = twelve_get_quote(sym)
        if td and td.get("price") is not None:
            new_p = round(float(td["price"]), 2)
            pct = td.get("percent_change")
            new_c = round(float(pct), 2) if pct is not None else None
        else:
            err = "twelve_miss"
    except Exception as e:
        err = str(e)[:2000]
        logger.warning("upsert_quote_twelve_warm fetch failed %s: %s", sym, err)

    prev_p = snap.price if snap else None
    prev_c = snap.change_percent if snap else None
    merged_p, merged_c = merge_quote_row(prev_p, prev_c, new_p, new_c)

    if snap is None:
        snap = MarketQuoteSnapshot(symbol=sym)
        db.add(snap)

    snap.price = merged_p
    snap.change_percent = merged_c
    snap.provider_source = "twelve"
    snap.last_attempt_at = attempt
    if new_p is not None and err is None:
        snap.last_success_at = attempt
        snap.last_error = None
        snap.is_stale = False
    else:
        snap.last_error = err or (snap.last_error if snap.last_error else None)
        snap.is_stale = bool(prev_p is not None and new_p is None)
        if snap.last_success_at is None and merged_p is None:
            snap.last_error = err or "no price"

    if merged_p is not None:
        try:
            ts = (snap.last_success_at or attempt).isoformat()
            cache_last_good_quote(sym, float(merged_p), merged_c, updated_at_iso=ts)
        except Exception:
            logger.debug("cache_last_good_quote after twelve warm failed", exc_info=True)

    return "ok" if new_p is not None and err is None else "fail"


def upsert_ohlcv_1m_twelve_warm(db: Session, symbol: str) -> str:
    """
    Warm 1M OHLCV via Twelve time_series (fills Redis), merges into OhlcvSnapshot for period 1M.
    Same interval/outputsize as API route PERIOD_TO_TWELVE['1M'].
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return "fail"
    if not is_twelve_supported_symbol(sym):
        return "skip"
    p = "1M"
    key = f"{sym}:{p}"
    iv, osz = TWELVE_WARM_1M_INTERVAL
    snap = db.get(OhlcvSnapshot, key)
    attempt = utcnow()
    err: str | None = None
    bars_list: list[dict] = []
    try:
        raw = twelve_get_time_series(sym, interval=iv, outputsize=osz)
        if raw:
            bars_list = [_bar_from_twelve_dict(b) for b in raw if b.get("time")]
        if not bars_list:
            err = "twelve_miss"
    except Exception as e:
        err = str(e)[:2000]
        logger.warning("upsert_ohlcv_1m_twelve_warm failed %s: %s", sym, err)

    if snap is None:
        snap = OhlcvSnapshot(snapshot_key=key, symbol=sym, period=p)
        db.add(snap)

    snap.last_attempt_at = attempt
    if bars_list and err is None:
        snap.bars = {"bars": bars_list}
        snap.provider_source = "twelve"
        snap.last_success_at = attempt
        snap.last_error = None
        snap.is_stale = False
    else:
        snap.last_error = err or (snap.last_error if snap.last_error else None)
        prev_bars = ((snap.bars or {}).get("bars", []) if snap.bars else [])
        snap.is_stale = bool(prev_bars and not bars_list)
        if snap.last_success_at is None and not bars_list:
            snap.last_error = err or "no bars"

    return "ok" if bars_list and err is None else "fail"


def upsert_quote_from_fetch(db: Session, symbol: str) -> MarketQuoteSnapshot:
    """
    Refresh quote: Twelve → Stooq → Yahoo (last). On failure, keep merged DB values (merge_quote_row).
    When Yahoo is in rate-limit cooldown and a DB snapshot exists, Yahoo is not called.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    sym_norm = normalize_user_symbol(sym)
    snap = db.get(MarketQuoteSnapshot, sym)
    attempt = utcnow()
    err: str | None = None
    new_p: float | None = None
    new_c: float | None = None
    provider_selected = "none"
    twelve_live = False
    stooq_live = False
    yahoo_skipped_cooldown = False
    twelve_routable = (
        is_twelve_configured()
        and route_quote_provider(sym_norm) == "twelve"
        and map_symbol_for_twelve(sym_norm) is not None
    )

    if twelve_routable:
        td_sym = map_symbol_for_twelve(sym_norm)
        if td_sym:
            try:
                td = _with_backoff(lambda: twelve_get_quote(td_sym))
                if td and td.get("price") is not None:
                    new_p = round(float(td["price"]), 2)
                    pct = td.get("percent_change")
                    new_c = round(float(pct), 2) if pct is not None else None
                    twelve_live = True
                    provider_selected = "twelve"
                else:
                    err = "twelve_miss"
                    logger.warning(
                        "market_pipeline quote symbol=%s stage=twelve_no_price fallback=stooq_yahoo",
                        sym_norm,
                    )
            except Exception as e:
                err = str(e)[:2000]
                logger.warning(
                    "market_pipeline quote symbol=%s stage=twelve_exception err=%s fallback=stooq_yahoo",
                    sym_norm,
                    err,
                )

    if not twelve_live:
        # Fallback #1: Yahoo
        if twelve_routable and twelve_rate_limited_recent():
            yahoo_skipped_cooldown = True
            provider_selected = "yahoo_skipped_twelve_cooldown"
            err = err or "twelve_rate_limited_recent"
            logger.info(
                "market_pipeline quote symbol=%s yahoo_skipped_due_to_recent_twelve_limit provider_selected=%s",
                sym_norm,
                provider_selected,
            )
        elif yahoo_provider_paused() and _quote_row_has_usable_snapshot(snap):
            yahoo_skipped_cooldown = True
            provider_selected = "yahoo_skipped_cooldown"
            err = None
            logger.info(
                "market_pipeline quote symbol=%s yahoo_skipped_due_to_cooldown "
                "provider_selected=yahoo_skipped_cooldown data_lineage=db_last_good reason=paused_and_has_snapshot",
                sym_norm,
            )
        else:
            try:
                q = _with_backoff(lambda: fetch_quote_yahoo(sym_norm))
                yahoo_used = bool(q.get("_yahoo_used"))
                new_p = q.get("price")
                new_c = q.get("change_percent")
                if new_p is not None:
                    new_p = round(float(new_p), 2)
                if new_c is not None:
                    new_c = round(float(new_c), 2)
                if new_p is not None:
                    provider_selected = "yahoo"
                    err = None
                else:
                    provider_selected = "yahoo" if yahoo_used else "none"
                    err = err or "yahoo_empty_or_paused"
            except Exception as e:
                err = str(e)[:2000]
                provider_selected = "yahoo"
                logger.warning("market_pipeline quote symbol=%s stage=yahoo_exception err=%s", sym_norm, err)

    # Fallback #2: fallback_provider (adapter currently backed by stooq).
    if not twelve_live and new_p is None:
        try:
            sq = fetch_quote_stooq(sym_norm)
            if sq.get("price") is not None:
                new_p = round(float(sq["price"]), 2)
                pct = sq.get("change_percent")
                new_c = round(float(pct), 2) if pct is not None else None
                stooq_live = True
                provider_selected = "fallback_provider"
                err = None
        except Exception as e:
            err = str(e)[:2000]
            logger.warning("market_pipeline quote symbol=%s stage=stooq_exception err=%s", sym_norm, err)

    prev_p = snap.price if snap else None
    prev_c = snap.change_percent if snap else None
    merged_p, merged_c = merge_quote_row(prev_p, prev_c, new_p, new_c)
    preserved_db_only = bool(prev_p is not None and new_p is None and merged_p == prev_p)

    if snap is None:
        snap = MarketQuoteSnapshot(symbol=sym)
        db.add(snap)

    snap.price = merged_p
    snap.change_percent = merged_c
    snap.provider_source = provider_selected
    snap.last_attempt_at = attempt
    live_ok = new_p is not None and err is None
    if live_ok:
        snap.last_success_at = attempt
        snap.last_error = None
        snap.is_stale = False
    else:
        snap.last_error = err or (snap.last_error if snap.last_error else None)
        snap.is_stale = bool(prev_p is not None and new_p is None)
        if snap.last_success_at is None and merged_p is None:
            snap.last_error = err or "no price"

    if twelve_live:
        data_lineage = "twelve"
    elif stooq_live:
        data_lineage = "fallback_provider"
    elif new_p is not None:
        data_lineage = "yahoo"
    elif yahoo_skipped_cooldown or preserved_db_only:
        data_lineage = "db_last_good"
    else:
        data_lineage = "none"
    freshness = "stale" if snap.is_stale else "fresh"

    logger.info(
        "market_pipeline quote symbol=%s provider_selected=%s twelve_live=%s stooq_live=%s "
        "fallback_used=%s live_fetch_ok=%s snapshot_fallback_merge=%s yahoo_skipped_due_to_cooldown=%s "
        "data_lineage=%s freshness=%s",
        sym_norm,
        provider_selected,
        twelve_live,
        stooq_live,
        bool(twelve_routable and not twelve_live),
        new_p is not None,
        preserved_db_only,
        yahoo_skipped_cooldown,
        data_lineage,
        freshness,
    )

    if merged_p is not None:
        try:
            ts = (snap.last_success_at or attempt).isoformat()
            cache_last_good_quote(sym, float(merged_p), merged_c, updated_at_iso=ts)
        except Exception:
            logger.debug("cache_last_good_quote after upsert failed", exc_info=True)

    return snap


# Periods we cache for OHLCV (aligned with frontend 1D, 5D, 1M, 6M, 1Y, MAX)
OHLCV_CACHE_PERIODS: tuple[str, ...] = ("1D", "5D", "1M", "6M", "1Y", "MAX")


def _bar_to_dict(bar) -> dict:
    """Convert OhlcvBar to JSON-serializable dict (time=unix seconds for CandleChart and comparison API)."""
    t = bar.t.replace(tzinfo=timezone.utc) if bar.t.tzinfo is None else bar.t
    return {
        "time": int(t.timestamp()),
        "open": round(bar.o, 4),
        "high": round(bar.h, 4),
        "low": round(bar.l, 4),
        "close": round(bar.c, 4),
        "volume": int(bar.v) if bar.v == int(bar.v) else round(bar.v, 0),
    }


def upsert_ohlcv_from_fetch(db: Session, symbol: str, period: str = "1M") -> OhlcvSnapshot | None:
    """
    OHLCV: Twelve time_series first when routable; else Stooq then Yahoo (see market.service.get_ohlcv).
    Preserves prior bars on failed refresh (stale flag).
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    sym_norm = normalize_user_symbol(sym)
    p = (period or "1M").upper()
    if p not in OHLCV_CACHE_PERIODS:
        p = "1M"
    key = f"{sym}:{p}"
    snap = db.get(OhlcvSnapshot, key)
    attempt = utcnow()
    err: str | None = None
    bars_list: list[dict] = []
    provider_selected = "none"
    twelve_live = False
    twelve_routable = (
        is_twelve_configured()
        and route_quote_provider(sym_norm) == "twelve"
        and map_symbol_for_twelve(sym_norm) is not None
    )

    if twelve_routable and p in PERIOD_TO_TWELVE_FETCH:
        td_sym = map_symbol_for_twelve(sym_norm)
        iv, osz = PERIOD_TO_TWELVE_FETCH[p]
        if td_sym:
            try:
                raw = _with_backoff(lambda: twelve_get_time_series(td_sym, interval=iv, outputsize=osz))
                if raw:
                    bars_list = [_bar_from_twelve_dict(b) for b in raw if b.get("time")]
                if bars_list:
                    twelve_live = True
                    provider_selected = "twelve"
                else:
                    err = "twelve_miss"
                    logger.warning("market_pipeline ohlcv symbol=%s period=%s stage=twelve_empty fallback=yahoo_fallback_provider", sym_norm, p)
            except Exception as e:
                err = str(e)[:2000]
                logger.warning(
                    "market_pipeline ohlcv symbol=%s period=%s stage=twelve_exception err=%s fallback=yahoo_fallback_provider",
                    sym_norm,
                    p,
                    err,
                )

    if not twelve_live:
        # Fallback #1 Yahoo
        if twelve_routable and twelve_rate_limited_recent():
            provider_selected = "yahoo_skipped_twelve_cooldown"
            err = err or "twelve_rate_limited_recent"
        else:
            try:
                raw_bars, ohlcv_src = get_ohlcv(symbol=sym_norm, period=p, provider_name="yahoo")
                bars_list = [_bar_to_dict(b) for b in raw_bars]
                if bars_list:
                    provider_selected = "yahoo"
                    err = None
            except Exception as e:
                err = str(e)[:2000]
                logger.warning("market_pipeline ohlcv symbol=%s period=%s stage=yahoo_exception err=%s", sym_norm, p, err)
                provider_selected = "yahoo"

    # Fallback #2 fallback_provider adapter (currently market provider stack).
    if not twelve_live and not bars_list:
        try:
            raw_bars, _ohlcv_src = get_ohlcv(symbol=sym_norm, period=p)
            bars_list = [_bar_to_dict(b) for b in raw_bars]
            if bars_list:
                provider_selected = "fallback_provider"
                err = None
            else:
                err = err or "no_bars_all_providers"
        except Exception as e:
            err = str(e)[:2000]
            logger.warning("market_pipeline ohlcv symbol=%s period=%s stage=fallback_provider_exception err=%s", sym_norm, p, err)
            provider_selected = "fallback_provider"

    prev_bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])
    preserved_db_only = bool(prev_bars and not bars_list)

    if snap is None:
        snap = OhlcvSnapshot(snapshot_key=key, symbol=sym, period=p)
        db.add(snap)

    snap.last_attempt_at = attempt
    live_ok = bool(bars_list) and err is None
    if live_ok:
        snap.bars = {"bars": bars_list}
        snap.provider_source = provider_selected
        snap.last_success_at = attempt
        snap.last_error = None
        snap.is_stale = False
    else:
        snap.last_error = err or (snap.last_error if snap.last_error else None)
        snap.is_stale = bool(prev_bars and not bars_list)
        if snap.last_success_at is None and not bars_list:
            snap.last_error = err or "no bars"

    if twelve_live:
        data_lineage = "twelve"
    elif bars_list and provider_selected == "yahoo":
        data_lineage = "yahoo"
    elif bars_list and provider_selected == "fallback_provider":
        data_lineage = "fallback_provider"
    elif preserved_db_only:
        data_lineage = "db_last_good"
    else:
        data_lineage = "none"
    freshness = "stale" if snap.is_stale else "fresh"

    logger.info(
        "market_pipeline ohlcv symbol=%s period=%s provider_selected=%s twelve_live=%s fallback_used=%s "
        "bars_ok=%s snapshot_fallback_merge=%s data_lineage=%s freshness=%s",
        sym_norm,
        p,
        provider_selected,
        twelve_live,
        bool(twelve_routable and not twelve_live),
        bool(bars_list),
        preserved_db_only,
        data_lineage,
        freshness,
    )

    return snap


def resolve_ohlcv_bars(
    db: Session, symbol: str, period: str = "1M"
) -> tuple[list[dict], OhlcvSnapshot | None, bool]:
    """
    Read persisted OHLCV only (GET /market/ohlcv). Celery refresh_market_ohlcv_snapshots fills snapshots.
    Returns (bars_json_list, snapshot_or_none, stale).
    """
    sym = (symbol or "").strip().upper()
    p = period.upper() if period else "1M"
    key = f"{sym}:{p}"
    snap = db.get(OhlcvSnapshot, key)
    bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])

    if snap is None:
        return bars, None, True
    stale = bool(snap.is_stale) or not bars
    return bars, snap, stale


def read_snapshot_rows_for_indices(db: Session, items: list[dict]) -> list[dict]:
    """
    Read-only: merge watchlist rows with persisted MarketQuoteSnapshot.
    Does not call external providers (worker/beat is responsible for refresh).
    """
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        sym = (item.get("symbol") or "").strip().upper()
        name = item.get("name") or sym
        if not sym:
            continue
        snap = db.get(MarketQuoteSnapshot, sym)
        if snap:
            lu = snap.last_success_at.isoformat() if snap.last_success_at else None
            row_stale = bool(snap.is_stale) or not lu
            row_ds = "stale_fallback" if row_stale else "snapshot"
            out.append(
                {
                    "name": name,
                    "symbol": sym,
                    "price": snap.price,
                    "change_percent": snap.change_percent,
                    "stale": row_stale,
                    "last_updated_at": lu,
                    "data_source": row_ds,
                }
            )
        else:
            fb = load_last_good_quote(sym)
            if fb and fb.get("updated_at_iso"):
                out.append(
                    {
                        "name": name,
                        "symbol": sym,
                        "price": fb["price"],
                        "change_percent": fb["change_percent"],
                        "stale": True,
                        "last_updated_at": fb["updated_at_iso"] or None,
                        "data_source": "stale_fallback",
                    }
                )
            else:
                out.append(
                    {
                        "name": name,
                        "symbol": sym,
                        "price": None,
                        "change_percent": None,
                        "stale": True,
                        "last_updated_at": None,
                        "data_source": "placeholder",
                    }
                )
    return out


def rows_for_indices(db: Session, items: list[dict]) -> list[dict]:
    """
    One upsert per symbol (merge + persist). Returns stale + last_updated_at for UI.
    """
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        sym = (item.get("symbol") or "").strip().upper()
        name = item.get("name") or sym
        if not sym:
            continue
        snap = upsert_quote_from_fetch(db, sym)
        lu = snap.last_success_at.isoformat() if snap.last_success_at else None
        out.append(
            {
                "name": name,
                "symbol": sym,
                "price": snap.price,
                "change_percent": snap.change_percent,
                "stale": bool(snap.is_stale),
                "last_updated_at": lu,
            }
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("commit market snapshots failed")
    return out


def schedule_market_snapshot_refresh_for_symbols(symbols: list[str]) -> None:
    """
    Enqueue async quote + OHLCV refresh for symbols (Celery). Safe no-op if broker unavailable.
    Does not block HTTP handlers.
    """
    syms = sorted({(s or "").strip().upper() for s in (symbols or []) if (s or "").strip()})
    if not syms:
        return
    try:
        from app.worker.tasks import refresh_market_snapshots_for_symbols

        refresh_market_snapshots_for_symbols.delay(syms)
    except Exception:
        logger.debug("schedule_market_snapshot_refresh_for_symbols skipped", exc_info=True)
