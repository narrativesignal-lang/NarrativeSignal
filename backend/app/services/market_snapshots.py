"""Persisted market quotes and OHLCV: refresh with fallback (never null-out successful values)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.data_subscription import MarketQuoteSnapshot, OhlcvSnapshot
from app.services.cache_fallback import merge_quote_row, utcnow
from app.services.market.service import fetch_quote, get_ohlcv

logger = logging.getLogger(__name__)


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

    return snap


# Periods we cache for OHLCV (aligned with frontend 1D, 5D, 1M, 6M, 1Y, MAX)
_OHLCV_PERIODS = ("1D", "5D", "1M", "6M", "1Y", "MAX")


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
    if p not in _OHLCV_PERIODS:
        p = "1M"
    key = f"{sym}:{p}"
    snap = db.get(OhlcvSnapshot, key)
    attempt = utcnow()
    err: str | None = None
    bars_list: list[dict] = []
    try:
        raw_bars = get_ohlcv(symbol=sym, period=p)
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
    Single source of truth for GET /market/ohlcv and batch: read snapshot, fetch on empty, commit/rollback.
    Returns (bars_json_list, snapshot_or_none, stale).
    """
    sym = (symbol or "").strip().upper()
    p = period.upper() if period else "1M"
    key = f"{sym}:{p}"
    snap = db.get(OhlcvSnapshot, key)
    bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])

    if not bars:
        try:
            upsert_ohlcv_from_fetch(db, sym, p)
            db.commit()
            snap = db.get(OhlcvSnapshot, key)
            bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])
        except Exception:
            db.rollback()
            snap = db.get(OhlcvSnapshot, key)
            bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])

    stale = True
    if snap:
        stale = bool(snap.is_stale)
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
        else:
            out.append(
                {
                    "name": name,
                    "symbol": sym,
                    "price": None,
                    "change_percent": None,
                    "stale": True,
                    "last_updated_at": None,
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
