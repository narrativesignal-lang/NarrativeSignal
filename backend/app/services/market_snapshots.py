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
from app.services.external_api_stats import bump as bump_external
from app.services.market.service import fetch_quote, get_ohlcv

logger = logging.getLogger(__name__)

QUOTE_LAST_GOOD_PREFIX = "market:quote:last_good:v1:"
QUOTE_LAST_GOOD_TTL_SEC = 86400 * 14


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


def upsert_quote_from_fetch(db: Session, symbol: str) -> MarketQuoteSnapshot:
    """Fetch one symbol; on failure or nulls, keep previous snapshot values."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    snap = db.get(MarketQuoteSnapshot, sym)
    attempt = utcnow()
    err: str | None = None
    new_p: float | None = None
    new_c: float | None = None
    try:
        q = fetch_quote(sym)
        bump_external("yahoo_quote", 1)
        new_p = q.get("price")
        new_c = q.get("change_percent")
        if new_p is not None:
            new_p = round(float(new_p), 2)
        if new_c is not None:
            new_c = round(float(new_c), 2)
    except Exception as e:
        err = str(e)[:2000]
        logger.warning("fetch_quote failed %s: %s", sym, err)

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
    Fetch OHLCV from Stooq, upsert for the given period. On success returns the snapshot.
    Fetches once per symbol; writes snapshot for the requested period. Does not overwrite existing
    successful data on fetch failure.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    p = (period or "1M").upper()
    if p not in OHLCV_CACHE_PERIODS:
        p = "1M"
    key = f"{sym}:{p}"
    snap = db.get(OhlcvSnapshot, key)
    attempt = utcnow()
    err: str | None = None
    bars_list: list[dict] = []
    try:
        raw_bars = get_ohlcv(symbol=sym, period=p)
        bump_external("market_ohlcv", 1)
        bars_list = [_bar_to_dict(b) for b in raw_bars]
    except Exception as e:
        err = str(e)[:2000]
        logger.warning("get_ohlcv failed %s:%s: %s", sym, p, err)

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
