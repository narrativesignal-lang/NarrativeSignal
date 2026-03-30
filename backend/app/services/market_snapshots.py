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
from app.services.market.service import fetch_quote_stooq, fetch_quote_yahoo, get_ohlcv
from app.services.market.yahoo_guard import yahoo_provider_paused
from app.services.market_provider_router import route_quote_provider
from app.services.symbol_mapping import map_symbol_for_twelve, normalize_user_symbol
from app.services.twelve_data_service import get_quote as twelve_get_quote
from app.services.twelve_data_service import get_time_series as twelve_get_time_series
from app.services.twelve_data_service import is_twelve_configured
from app.services.twelve_symbol_support import is_twelve_supported_symbol
from app.services.twelve_warm_pool import TWELVE_WARM_1M_INTERVAL

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
        and route_quote_provider(sym_norm) == "twelvedata"
        and map_symbol_for_twelve(sym_norm) is not None
    )

    if twelve_routable:
        td_sym = map_symbol_for_twelve(sym_norm)
        if td_sym:
            try:
                td = twelve_get_quote(td_sym)
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
        try:
            sq = fetch_quote_stooq(sym_norm)
            if sq.get("price") is not None:
                new_p = round(float(sq["price"]), 2)
                pct = sq.get("change_percent")
                new_c = round(float(pct), 2) if pct is not None else None
                stooq_live = True
                provider_selected = "stooq_fallback"
                err = None
        except Exception as e:
            err = str(e)[:2000]
            logger.warning("market_pipeline quote symbol=%s stage=stooq_exception err=%s", sym_norm, err)

    if not twelve_live and not stooq_live:
        if yahoo_provider_paused() and _quote_row_has_usable_snapshot(snap):
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
                q = fetch_quote_yahoo(sym_norm)
                yahoo_used = bool(q.get("_yahoo_used"))
                new_p = q.get("price")
                new_c = q.get("change_percent")
                if new_p is not None:
                    new_p = round(float(new_p), 2)
                if new_c is not None:
                    new_c = round(float(new_c), 2)
                if new_p is not None:
                    provider_selected = "yahoo_fallback"
                    err = None
                else:
                    provider_selected = "yahoo_fallback" if yahoo_used else "none"
                    err = err or "yahoo_empty_or_paused"
            except Exception as e:
                err = str(e)[:2000]
                provider_selected = "yahoo_fallback"
                logger.warning("market_pipeline quote symbol=%s stage=yahoo_exception err=%s", sym_norm, err)

    prev_p = snap.price if snap else None
    prev_c = snap.change_percent if snap else None
    merged_p, merged_c = merge_quote_row(prev_p, prev_c, new_p, new_c)
    preserved_db_only = bool(prev_p is not None and new_p is None and merged_p == prev_p)

    if snap is None:
        snap = MarketQuoteSnapshot(symbol=sym)
        db.add(snap)

    snap.price = merged_p
    snap.change_percent = merged_c
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
        data_lineage = "stooq_fallback"
    elif new_p is not None:
        data_lineage = "yahoo_fallback"
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
        and route_quote_provider(sym_norm) == "twelvedata"
        and map_symbol_for_twelve(sym_norm) is not None
    )

    if twelve_routable and p in PERIOD_TO_TWELVE_FETCH:
        td_sym = map_symbol_for_twelve(sym_norm)
        iv, osz = PERIOD_TO_TWELVE_FETCH[p]
        if td_sym:
            try:
                raw = twelve_get_time_series(td_sym, interval=iv, outputsize=osz)
                if raw:
                    bars_list = [_bar_from_twelve_dict(b) for b in raw if b.get("time")]
                if bars_list:
                    twelve_live = True
                    provider_selected = "twelve"
                else:
                    err = "twelve_miss"
                    logger.warning(
                        "market_pipeline ohlcv symbol=%s period=%s stage=twelve_empty fallback=stooq_yahoo",
                        sym_norm,
                        p,
                    )
            except Exception as e:
                err = str(e)[:2000]
                logger.warning(
                    "market_pipeline ohlcv symbol=%s period=%s stage=twelve_exception err=%s fallback=stooq_yahoo",
                    sym_norm,
                    p,
                    err,
                )

    if not twelve_live:
        try:
            raw_bars, ohlcv_src = get_ohlcv(symbol=sym_norm, period=p)
            bars_list = [_bar_to_dict(b) for b in raw_bars]
            if bars_list:
                provider_selected = ohlcv_src if ohlcv_src in ("stooq_fallback", "yahoo_fallback") else "fallback"
                err = None
            else:
                provider_selected = ohlcv_src or "none"
                err = err or "no_bars_all_providers"
        except Exception as e:
            err = str(e)[:2000]
            logger.warning("market_pipeline ohlcv symbol=%s period=%s stage=fallback_exception err=%s", sym_norm, p, err)
            provider_selected = "yahoo_fallback"

    prev_bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])
    preserved_db_only = bool(prev_bars and not bars_list)

    if snap is None:
        snap = OhlcvSnapshot(snapshot_key=key, symbol=sym, period=p)
        db.add(snap)

    snap.last_attempt_at = attempt
    live_ok = bool(bars_list) and err is None
    if live_ok:
        snap.bars = {"bars": bars_list}
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
    elif bars_list and provider_selected == "yahoo_fallback":
        data_lineage = "yahoo_fallback"
    elif bars_list and provider_selected == "stooq_fallback":
        data_lineage = "stooq_fallback"
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
