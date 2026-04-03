from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis
from fastapi import APIRouter, Depends, Query, status, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional
from app.core.config import settings
from app.db.session import get_db
from app.models.macro_index import MacroIndex
from app.models.portfolio import Instrument
from app.models.user import User
from app.services.market_indices_config import DEFAULT_INDICES_BY_CATEGORY, MAX_INDICES_PER_CATEGORY
from app.models.data_subscription import MarketQuoteSnapshot

from app.services.market_snapshots import (
    load_last_good_quote,
    read_snapshot_rows_for_indices,
    resolve_ohlcv_bars,
    schedule_market_snapshot_refresh_for_symbols,
)
from app.services.twelve_data_service import get_quote as twelve_get_quote
from app.services.twelve_data_service import get_time_series as twelve_get_time_series
from app.services.twelve_data_service import search_symbol as twelve_search_symbol
from app.services.instrument_search_service import (
    ASSET_CLASS_BY_CATEGORY_SEARCH,
    twelve_search_row_matches_filters,
    upsert_instrument_from_twelve_symbol_row,
)
from app.services.market_provider_router import route_quote_provider, route_time_series_provider
from app.services.symbol_mapping import map_symbol_for_twelve, normalize_user_symbol
from app.services.subscriptions import register_instrument_quote_subscription
from app.services.core_data_diag import record_cold_empty, record_first_paint_envelope, record_snapshot_hit

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_source_from_stale(stale: bool) -> str:
    return "stale_fallback" if stale else "snapshot"


def _ensure_instrument_twelve(db: Session, row: dict) -> str:
    inst, _ = upsert_instrument_from_twelve_symbol_row(db, row, provider="twelvedata")
    return str(inst.id)


def _db_instrument_search_fallback(
    db: Session,
    q: str,
    asset_class: str | None,
    category: str | None,
    exchange: str | None,
    limit: int = 20,
) -> list[dict]:
    term = (q or "").strip()
    if not term:
        return []
    s = f"%{term}%"
    stmt = (
        select(Instrument)
        .where(Instrument.is_active.is_(True))
        .where(
            or_(
                Instrument.symbol.ilike(s),
                Instrument.display_name.ilike(s),
                Instrument.description.ilike(s),
            )
        )
    )
    if asset_class:
        stmt = stmt.where(Instrument.asset_class == asset_class)
    elif category:
        cat_lower = category.strip().lower()
        if cat_lower == "hong kong" or cat_lower == "hk":
            stmt = stmt.where(
                (Instrument.country == "HK") | (Instrument.exchange == "HKEX") | (Instrument.market == "HK")
            )
        elif cat_lower in ASSET_CLASS_BY_CATEGORY_SEARCH:
            stmt = stmt.where(Instrument.asset_class == ASSET_CLASS_BY_CATEGORY_SEARCH[cat_lower])
    if exchange:
        stmt = stmt.where(Instrument.exchange == exchange)
    rows = db.scalars(stmt.limit(100)).all()

    def score(inst: Instrument) -> int:
        q_norm = term.lower()
        sym = (inst.symbol or "").lower()
        name = (inst.display_name or "").lower()
        desc = (inst.description or "").lower()
        sc = 0
        if sym == q_norm:
            sc += 100
        elif sym.startswith(q_norm):
            sc += 70
        elif q_norm in sym:
            sc += 50
        if q_norm in name:
            sc += 30
        if q_norm in desc:
            sc += 10
        return sc

    ranked = sorted(rows, key=score, reverse=True)[:limit]
    return [
        {
            "symbol": r.symbol,
            "name": r.display_name or r.symbol,
            "exchange": r.exchange or "",
            "type": r.asset_class,
            "instrument_id": str(r.id),
        }
        for r in ranked
    ]


def _iso_to_unix_bar(bar: dict) -> dict:
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
    return {
        "time": unix,
        "open": float(bar.get("open") or 0),
        "high": float(bar.get("high") or 0),
        "low": float(bar.get("low") or 0),
        "close": float(bar.get("close") or 0),
        "volume": float(bar.get("volume") or 0),
    }


PERIOD_TO_TWELVE: dict[str, tuple[str, int]] = {
    "1D": ("1day", 14),
    "5D": ("1day", 10),
    "1M": ("1day", 40),
    "6M": ("1day", 200),
    "1Y": ("1day", 400),
    "MAX": ("1week", 520),
}


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
    """Read-only quote response from local snapshot cache (no direct provider call in request path)."""
    raw_in = symbol
    sym = normalize_user_symbol(symbol)
    logger.info("symbol_normalized from=%s to=%s", raw_in, sym)
    quote_prov = route_quote_provider(symbol)
    logger.info("provider_route kind=quote symbol=%s provider=%s request_mode=snapshot_only", sym, quote_prov)

    snap = db.get(MarketQuoteSnapshot, sym)
    lg = load_last_good_quote(sym)
    price = None
    pct = None
    chg = None
    lu = None
    st = True
    if snap and snap.price is not None:
        price = float(snap.price) if snap.price is not None else None
        pct = float(snap.change_percent) if snap.change_percent is not None else None
        lu = snap.last_success_at.isoformat() if snap.last_success_at else None
        st = bool(snap.is_stale)
    elif lg and lg.get("price") is not None:
        price = float(lg["price"])
        pct = float(lg["change_percent"]) if lg.get("change_percent") is not None else None
        lu = str(lg.get("updated_at_iso") or "") or None
        st = True

    if price is None:
        payload = {"symbol": sym, "price": None, "change_percent": None, "change": None, "timestamp": None}
        record_snapshot_hit("market_quote_empty")
        return {
            "data": payload,
            "last_updated_at": None,
            "data_updated_at": None,
            "data_source": "unavailable",
            "provider": "unavailable",
            "stale": True,
            "availability": "unavailable",
            **payload,
        }

    if pct is not None and chg is None:
        try:
            prev = price / (1.0 + float(pct) / 100.0) if price is not None and pct is not None else None
            chg = round(float(price) - float(prev), 6) if prev else None
        except Exception:
            chg = None

    record_snapshot_hit("market_quote")
    payload = {"symbol": sym, "price": price, "change_percent": pct, "change": chg, "timestamp": lu}
    provider_source = (snap.provider_source if snap else None) or "snapshot"
    data_source = "stale_fallback" if st else "snapshot"
    return {
        "data": payload,
        **payload,
        "stale": st,
        "last_updated_at": lu,
        "data_updated_at": lu,
        "data_source": data_source,
        "provider": provider_source,
        "availability": "delayed" if st else "ready",
    }


@router.get("/search")
def market_search(
    q: str = Query(..., min_length=1, max_length=120),
    asset_class: str | None = Query(None),
    category: str | None = Query(None),
    exchange: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    td_rows = twelve_search_symbol(q)
    filtered = [r for r in td_rows if twelve_search_row_matches_filters(r, asset_class, category)]
    if exchange:
        exu = exchange.strip().upper()
        filtered = [r for r in filtered if (r.get("exchange") or "").strip().upper() == exu]
    use = filtered[:25] if filtered else []
    rows: list[dict] = []
    data_source = "twelvedata"
    if use:
        try:
            for r in use:
                iid = _ensure_instrument_twelve(db, r)
                rows.append({**r, "instrument_id": iid})
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("market_search instrument upsert")
            rows = []
    if not rows:
        rows = _db_instrument_search_fallback(db, q, asset_class, category, exchange, 20)
        data_source = "fallback"
    return {"data": rows, "data_source": data_source}


@router.get("/time_series")
def time_series(
    symbol: str = Query(..., min_length=1, max_length=30),
    interval: str | None = Query(None, max_length=16),
    outputsize: int | None = Query(None, ge=1, le=5000),
    period: str = Query("1M", max_length=8),
    db: Session = Depends(get_db),
) -> dict:
    raw_in = symbol
    sym = normalize_user_symbol(symbol)
    logger.info("symbol_normalized from=%s to=%s", raw_in, sym)
    ts_prov = route_time_series_provider(symbol)
    logger.info("provider_route kind=time_series symbol=%s provider=%s request_mode=snapshot_only", sym, ts_prov)
    p = period.upper() if period else "1M"
    if interval and outputsize is not None:
        iv, osz = interval.strip(), int(outputsize)
    else:
        iv, osz = PERIOD_TO_TWELVE.get(p, ("1day", 100))
    bars: list[dict] = []
    data_source = "snapshot"
    lu = datetime.now(timezone.utc).isoformat()
    stale = False
    snap = None
    bars, snap, stale = resolve_ohlcv_bars(db, sym, p)
    lu = snap.last_success_at.isoformat() if snap and snap.last_success_at else lu
    if not bars:
        data_source = "unavailable"
    record_snapshot_hit("market_time_series")
    prov = (snap.provider_source if snap else None) or ("unavailable" if data_source == "unavailable" else "snapshot")
    payload = {"symbol": sym, "period": p, "provider": prov, "bars": bars}
    return {
        "data": payload,
        **payload,
        "last_updated_at": lu,
        "data_updated_at": lu,
        "data_source": data_source,
        "stale": stale,
        "availability": "unavailable" if data_source == "unavailable" else ("delayed" if stale else "ready"),
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

    try:
        rows = read_snapshot_rows_for_indices(db, all_items)
    except Exception:
        logger.exception("market indices: snapshot read failed category=%s", category)
        record_snapshot_hit("market_indices_error")
        record_first_paint_envelope("market_indices", loading_state="placeholder", data_source="placeholder")
        return {
            "data": [],
            "last_updated_at": None,
            "data_updated_at": None,
            "data_source": "placeholder",
            "loading_state": "placeholder",
            "message": "Index watchlist is temporarily unavailable (snapshot read failed).",
            "stale": True,
        }
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


@router.delete("/indices", status_code=status.HTTP_200_OK)
def delete_index(
    category: str = Query(..., min_length=1, max_length=80),
    symbol: str = Query(..., min_length=1, max_length=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Delete a user-added index row by (category, symbol).
    Defaults are not stored per-user and cannot be deleted.
    """
    cat = category.strip()
    sym = normalize_user_symbol(symbol)
    row = db.scalar(
        select(MacroIndex).where(
            MacroIndex.user_id == current_user.id,
            MacroIndex.category == cat,
            MacroIndex.symbol == sym,
        )
    )
    if not row:
        # Idempotent delete: nothing to remove.
        return {"ok": True, "deleted": False}
    db.delete(row)
    db.commit()
    try:
        _get_redis().delete(f"macro_indices_prices:{cat}")
    except Exception:
        pass
    return {"ok": True, "deleted": True}

