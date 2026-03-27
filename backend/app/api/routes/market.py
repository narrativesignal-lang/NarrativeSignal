from __future__ import annotations

import logging
import redis
from fastapi import APIRouter, Depends, Query, status, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional
from app.core.config import settings
from app.db.session import get_db
from app.models.macro_index import MacroIndex
from app.models.user import User
from app.services.market_indices_config import DEFAULT_INDICES_BY_CATEGORY, MAX_INDICES_PER_CATEGORY
from app.models.data_subscription import MarketQuoteSnapshot

from app.services.market_snapshots import (
    read_snapshot_rows_for_indices,
    resolve_ohlcv_bars,
    upsert_quote_from_fetch,
)
from app.services.subscriptions import register_instrument_quote_subscription

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/quote")
def quote(symbol: str = Query(..., min_length=1, max_length=30), db: Session = Depends(get_db)) -> dict:
    """Return latest persisted quote snapshot only (no external call in GET)."""
    sym = symbol.upper()
    snap = db.get(MarketQuoteSnapshot, sym)
    if not snap:
        payload = {"symbol": sym, "price": None, "change_percent": None}
        return {
            "data": payload,
            "last_updated_at": None,
            "stale": True,
            **payload,
        }
    payload = {"symbol": sym, "price": snap.price, "change_percent": snap.change_percent}
    return {
        "data": payload,
        **payload,
        "stale": bool(snap.is_stale),
        "last_updated_at": snap.last_success_at.isoformat() if snap.last_success_at else None,
    }


class OhlcvBatchBody(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=24)
    period: str = Field(default="1M", max_length=8)


@router.get("/ohlcv")
def ohlcv(
    symbol: str = Query(..., min_length=1, max_length=30),
    period: str = Query("1M"),
    provider: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    sym = symbol.upper()
    p = period.upper() if period else "1M"
    bars, snap, stale = resolve_ohlcv_bars(db, sym, p)
    payload = {
        "symbol": sym,
        "period": p,
        "provider": (provider or "snapshot"),
        "bars": bars,
    }
    return {
        "data": payload,
        **payload,
        "last_updated_at": snap.last_success_at.isoformat() if snap and snap.last_success_at else None,
        "stale": stale,
    }


@router.post("/ohlcv-batch")
def ohlcv_batch(body: OhlcvBatchBody, db: Session = Depends(get_db)) -> dict:
    """Same resolution path as GET /ohlcv, multiple symbols in one request (order preserved, deduped)."""
    p = (body.period or "1M").upper()
    unique_symbols: list[str] = []
    seen: set[str] = set()
    for raw in body.symbols:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            unique_symbols.append(sym)
    items: dict[str, dict] = {}
    for sym in unique_symbols:
        bars, snap, stale = resolve_ohlcv_bars(db, sym, p)
        items[sym] = {
            "symbol": sym,
            "period": p,
            "provider": "snapshot",
            "bars": bars,
            "last_updated_at": snap.last_success_at.isoformat() if snap and snap.last_success_at else None,
            "stale": stale,
        }
    payload = {"period": p, "items": items}
    return {"data": payload, **payload}


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


@router.get("/indices")
def get_indices(
    category: str = Query("general", min_length=1, max_length=80),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict:
    """
    Merge defaults + user indices, then return latest persisted quotes from market_quote_snapshots.
    Does not hit external providers on this request — Celery refresh_market_quotes keeps snapshots warm.
    """
    # Normalize category for default lookup (frontend may send "General" etc.)
    category_lower = category.strip().lower()
    default_list = list(DEFAULT_INDICES_BY_CATEGORY.get(category_lower, []))
    all_items: list[dict] = list(default_list)

    # Load user-added indices for this category (exact category string as stored)
    if current_user:
        user_indices = db.scalars(
            select(MacroIndex).where(
                MacroIndex.user_id == current_user.id,
                MacroIndex.category == category,
            ).order_by(MacroIndex.created_at.asc())
        ).all()
        for mi in user_indices:
            all_items.append({"name": mi.name, "symbol": mi.symbol})

    # Limit total to 10
    all_items = all_items[:MAX_INDICES_PER_CATEGORY]

    if not all_items:
        return {"data": [], "last_updated_at": None, "stale": True}

    rows = read_snapshot_rows_for_indices(db, all_items)

    # Best-effort live fetch when snapshots are empty (e.g. dev without Celery). Bounded: ≤10 symbols.
    if any(r.get("price") is None for r in rows):
        try:
            for item in all_items:
                sym = (item.get("symbol") or "").strip().upper()
                if sym:
                    upsert_quote_from_fetch(db, sym)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("lazy quote refresh for indices failed")
        rows = read_snapshot_rows_for_indices(db, all_items)

    last_updated_at = None
    stale = False
    for r in rows:
        if not r.get("last_updated_at"):
            r["stale"] = True
        if r.get("stale"):
            stale = True
        if r.get("last_updated_at"):
            if last_updated_at is None or str(r["last_updated_at"]) > str(last_updated_at):
                last_updated_at = r["last_updated_at"]
    return {"data": rows, "last_updated_at": last_updated_at, "stale": stale}


@router.post("/indices", status_code=status.HTTP_201_CREATED)
def add_index(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    name = str(payload.get("name", "")).strip()
    symbol = str(payload.get("symbol", "")).strip()
    asset_type = str(payload.get("asset_type", "")).strip() or "index"
    category = str(payload.get("category", "")).strip()
    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    if not name or not symbol:
        raise HTTPException(status_code=400, detail="name and symbol are required")
    default_count = len(DEFAULT_INDICES_BY_CATEGORY.get(category.strip().lower(), []))
    user_count = db.scalar(
        select(func.count()).select_from(MacroIndex).where(
            MacroIndex.user_id == current_user.id,
            MacroIndex.category == category,
        )
    ) or 0
    if default_count + user_count >= MAX_INDICES_PER_CATEGORY:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_INDICES_PER_CATEGORY} items per category",
        )
    mi = MacroIndex(
        user_id=current_user.id,
        category=category,
        name=name,
        symbol=symbol,
        asset_type=asset_type,
    )
    db.add(mi)
    register_instrument_quote_subscription(db, current_user.id, symbol)
    db.commit()
    db.refresh(mi)
    try:
        upsert_quote_from_fetch(db, symbol)
        db.commit()
    except Exception:
        db.rollback()
    r = _get_redis()
    try:
        r.delete(f"macro_indices_prices:{category}")
    except Exception:
        pass
    return {"id": str(mi.id), "category": mi.category, "name": mi.name, "symbol": mi.symbol, "asset_type": mi.asset_type}

