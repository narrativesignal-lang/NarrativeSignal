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
    schedule_market_snapshot_refresh_for_symbols,
)
from app.services.subscriptions import register_instrument_quote_subscription
from app.services.core_data_diag import record_cold_empty, record_first_paint_envelope, record_snapshot_hit

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_source_from_stale(stale: bool) -> str:
    return "stale_fallback" if stale else "snapshot"


def _indices_top_envelope(rows: list[dict]) -> tuple[str, str, str | None, bool]:
    """Top-level data_source, loading_state, optional message, aggregate stale."""
    if not rows:
        return "placeholder", "placeholder", "No indices configured for this category yet.", True
    sources = [str(r.get("data_source") or "snapshot") for r in rows]
    all_ph = all(s == "placeholder" for s in sources)
    any_ph = any(s == "placeholder" for s in sources)
    any_stale = any(r.get("stale") for r in rows)
    any_sf = any(s == "stale_fallback" for s in sources)
    if all_ph:
        return "placeholder", "placeholder", "Quotes are warming; placeholder rows keep layout stable.", True
    if any_ph:
        return "stale_fallback", "warming", "Some symbols are still loading; last-known quotes or placeholders shown.", True
    if any_sf or any_stale:
        return "stale_fallback", "stale", None, True
    return "snapshot", "ready", None, False


@router.get("/quote")
def quote(symbol: str = Query(..., min_length=1, max_length=30), db: Session = Depends(get_db)) -> dict:
    """Return latest persisted quote snapshot only (no external call in GET)."""
    sym = symbol.upper()
    snap = db.get(MarketQuoteSnapshot, sym)
    if not snap:
        payload = {"symbol": sym, "price": None, "change_percent": None}
        record_snapshot_hit("market_quote_empty")
        return {
            "data": payload,
            "last_updated_at": None,
            "data_updated_at": None,
            "data_source": "stale_fallback",
            "stale": True,
            **payload,
        }
    record_snapshot_hit("market_quote")
    st = bool(snap.is_stale)
    payload = {"symbol": sym, "price": snap.price, "change_percent": snap.change_percent}
    lu = snap.last_success_at.isoformat() if snap.last_success_at else None
    return {
        "data": payload,
        **payload,
        "stale": st,
        "last_updated_at": lu,
        "data_updated_at": lu,
        "data_source": _data_source_from_stale(st),
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
    record_snapshot_hit("market_ohlcv")
    payload = {
        "symbol": sym,
        "period": p,
        "provider": (provider or "snapshot"),
        "bars": bars,
    }
    lu = snap.last_success_at.isoformat() if snap and snap.last_success_at else None
    return {
        "data": payload,
        **payload,
        "last_updated_at": lu,
        "data_updated_at": lu,
        "data_source": _data_source_from_stale(stale),
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
    batch_stale = False
    latest: str | None = None
    for sym in unique_symbols:
        bars, snap, stale = resolve_ohlcv_bars(db, sym, p)
        if stale:
            batch_stale = True
        lu = snap.last_success_at.isoformat() if snap and snap.last_success_at else None
        if lu and (latest is None or lu > latest):
            latest = lu
        items[sym] = {
            "symbol": sym,
            "period": p,
            "provider": "snapshot",
            "bars": bars,
            "last_updated_at": lu,
            "stale": stale,
        }
    record_snapshot_hit("market_ohlcv_batch")
    payload = {"period": p, "items": items}
    return {
        "data": payload,
        **payload,
        "last_updated_at": latest,
        "data_updated_at": latest,
        "data_source": _data_source_from_stale(batch_stale),
        "stale": batch_stale,
    }


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
    Never calls Yahoo on GET — Celery refresh_market_quotes (15m) keeps snapshots warm; missing rows
    return nulls with stale until the next refresh.
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
        record_snapshot_hit("market_indices_empty")
        record_cold_empty("market_indices")
        record_first_paint_envelope("market_indices", loading_state="placeholder", data_source="placeholder")
        return {
            "data": [],
            "last_updated_at": None,
            "data_updated_at": None,
            "data_source": "placeholder",
            "loading_state": "placeholder",
            "message": "No indices configured for this category yet.",
            "stale": True,
        }

    rows = read_snapshot_rows_for_indices(db, all_items)
    record_snapshot_hit("market_indices")

    last_updated_at = None
    for r in rows:
        if not r.get("last_updated_at"):
            r["stale"] = True
        if r.get("last_updated_at"):
            if last_updated_at is None or str(r["last_updated_at"]) > str(last_updated_at):
                last_updated_at = r["last_updated_at"]

    top_ds, top_ls, top_msg, top_stale = _indices_top_envelope(rows)
    record_first_paint_envelope("market_indices", loading_state=top_ls, data_source=top_ds)
    need = [(r.get("symbol") or "") for r in rows if r.get("data_source") == "placeholder"]
    if need:
        schedule_market_snapshot_refresh_for_symbols(need)

    return {
        "data": rows,
        "last_updated_at": last_updated_at,
        "data_updated_at": last_updated_at,
        "data_source": top_ds,
        "loading_state": top_ls,
        "message": top_msg,
        "stale": top_stale,
    }


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
    schedule_market_snapshot_refresh_for_symbols([symbol])
    r = _get_redis()
    try:
        r.delete(f"macro_indices_prices:{category}")
    except Exception:
        pass
    return {"id": str(mi.id), "category": mi.category, "name": mi.name, "symbol": mi.symbol, "asset_type": mi.asset_type}

