"""Instrument discovery: Twelve search row mapping, filters, and DB upsert (symbol + asset_class + exchange)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.portfolio import Instrument
from app.services.symbol_mapping import normalize_user_symbol
from app.services.twelve_data_service import is_twelve_configured, search_symbol as twelve_search_symbol

logger = logging.getLogger(__name__)

# Aligned with api/routes/market.py and portfolios category filters
ASSET_CLASS_BY_CATEGORY_SEARCH: dict[str, str] = {
    "stock": "equity",
    "etf": "etf",
    "index": "index",
    "futures": "futures",
    "crypto": "crypto",
}


def twelve_row_from_bind_fields(
    *,
    symbol: str,
    asset_class: str,
    exchange: str | None,
    display_name: str | None,
) -> dict[str, Any]:
    """
    Build a Twelve-shaped row for upsert_instrument_from_twelve_symbol_row from UI bind payload.
    """
    typ = {
        "equity": "Common Stock",
        "etf": "ETF",
        "crypto": "Cryptocurrency",
        "futures": "Future",
        "index": "Index",
    }.get((asset_class or "").strip().lower(), "Common Stock")
    sym = normalize_user_symbol(symbol)
    return {
        "symbol": sym,
        "name": ((display_name or sym) or sym)[:120],
        "exchange": (exchange or "").strip(),
        "type": typ,
    }


def map_twelve_type_to_asset_class(t: str) -> str:
    s = (t or "").lower()
    if "etf" in s:
        return "etf"
    if "crypto" in s or "digital currency" in s:
        return "crypto"
    if "future" in s:
        return "futures"
    if "index" in s:
        return "index"
    return "equity"


def twelve_row_identity_key(row: dict[str, Any]) -> tuple[str, str, str]:
    """Match key for deduping Twelve rows against Instrument rows (symbol, asset_class, exchange)."""
    sym = normalize_user_symbol(str(row.get("symbol") or ""))
    ac = map_twelve_type_to_asset_class(str(row.get("type") or ""))
    ex = (row.get("exchange") or "").strip().upper()
    return (sym, ac, ex)


def ephemeral_instrument_id(sym: str, asset_class: str, exchange_upper: str) -> str:
    h = hashlib.sha256(f"{sym}\0{asset_class}\0{exchange_upper}".encode()).hexdigest()
    return f"ext-pending-{h[:32]}"


def score_twelve_row_for_query(row: dict[str, Any], q_norm: str) -> int:
    sym = normalize_user_symbol(str(row.get("symbol") or "")).lower()
    name = (str(row.get("name") or "") or "").lower()
    sc = 0
    if sym == q_norm:
        sc += 100
    elif sym.startswith(q_norm):
        sc += 70
    elif q_norm in sym:
        sc += 50
    if q_norm in name:
        sc += 30
    return sc


def twelve_rows_to_ephemeral_hit_dicts(
    rows: list[dict[str, Any]],
    *,
    q_norm: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Payload dicts for InstrumentSearchHit (data_origin=external_fallback)."""
    ranked = sorted(rows, key=lambda r: score_twelve_row_for_query(r, q_norm), reverse=True)[:limit]
    out: list[dict[str, Any]] = []
    for r in ranked:
        sym = normalize_user_symbol(str(r.get("symbol") or ""))
        if not sym:
            continue
        ac = map_twelve_type_to_asset_class(str(r.get("type") or ""))
        ex_raw = (r.get("exchange") or "").strip()
        ex_val = ex_raw or None
        ex_upper = ex_raw.upper()
        name = ((r.get("name") or sym) or sym)[:120]
        out.append(
            {
                "id": ephemeral_instrument_id(sym, ac, ex_upper),
                "symbol": sym,
                "display_name": name,
                "asset_class": ac,
                "market": ex_val,
                "exchange": ex_val,
                "description": None,
                "country": None,
                "currency": None,
                "data_origin": "external_fallback",
            }
        )
    return out


def filter_twelve_instrument_search_rows(
    query: str,
    *,
    asset_class: str | None,
    category: str | None,
    exchange: str | None,
    max_rows: int = 25,
) -> list[dict[str, Any]]:
    """Twelve symbol_search rows after the same filters as local portfolio search (no DB)."""
    if not is_twelve_configured():
        logger.info(
            "instrument_search external_skip reason=no_twelve_key q=%r",
            (query or "")[:80],
        )
        return []

    raw_rows = twelve_search_symbol(query)
    filtered: list[dict[str, Any]] = []
    for r in raw_rows:
        if not twelve_search_row_matches_filters(r, asset_class, category):
            continue
        if exchange:
            rex = (r.get("exchange") or "").strip().upper()
            if rex != exchange.strip().upper():
                continue
        filtered.append(r)
        if len(filtered) >= max_rows:
            break
    return filtered


def persist_twelve_instrument_rows(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    provider: str,
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for r in rows:
        try:
            _, created = upsert_instrument_from_twelve_symbol_row(db, r, provider=provider)
            if created:
                inserted += 1
            else:
                updated += 1
        except Exception:
            logger.warning(
                "instrument_search external_persist_row_failed row=%r",
                r,
                exc_info=True,
            )
    if inserted or updated:
        logger.info(
            "instrument_search external_persist rows=%d inserted=%d updated=%d provider=%s",
            len(rows),
            inserted,
            updated,
            provider,
        )
    return inserted, updated


def twelve_search_row_matches_filters(
    row: dict[str, Any],
    asset_class: str | None,
    category: str | None,
) -> bool:
    typ = (row.get("type") or "").lower()
    mapping = map_twelve_type_to_asset_class(typ)
    if category:
        cl = category.strip().lower()
        if cl in ("hong kong", "hk"):
            ex = (row.get("exchange") or "").upper()
            if not ("HK" in ex or "HONG" in ex or "HKEX" in ex):
                return False
        elif cl in ASSET_CLASS_BY_CATEGORY_SEARCH:
            if mapping != ASSET_CLASS_BY_CATEGORY_SEARCH[cl]:
                return False
    if asset_class and mapping != asset_class.strip().lower():
        return False
    return True


def _exchange_match_clause(exchange: str | None):
    raw = (exchange or "").strip().upper()
    if raw:
        return func.upper(func.coalesce(Instrument.exchange, "")) == raw
    return func.coalesce(func.trim(Instrument.exchange), "") == ""


def upsert_instrument_from_twelve_symbol_row(
    db: Session,
    row: dict[str, Any],
    *,
    provider: str,
) -> tuple[Instrument, bool]:
    """
    Insert or update one Instrument from a Twelve symbol_search row.
    Uniqueness: normalized symbol + asset_class + exchange (empty exchange groups together).

    Returns (instrument, created_new).
    """
    symbol_norm = normalize_user_symbol(str(row.get("symbol") or ""))
    if not symbol_norm:
        raise ValueError("symbol required")

    raw_ex = (row.get("exchange") or "").strip()
    exchange_val = raw_ex or None
    name = ((row.get("name") or symbol_norm) or symbol_norm)[:120]
    asset_class = map_twelve_type_to_asset_class(str(row.get("type") or ""))
    prov_sym = str(row.get("symbol") or "").strip().upper() or symbol_norm

    stmt = (
        select(Instrument)
        .where(
            and_(
                Instrument.symbol == symbol_norm,
                Instrument.asset_class == asset_class,
                Instrument.is_active.is_(True),
                _exchange_match_clause(exchange_val),
            )
        )
        .limit(1)
    )
    inst = db.scalars(stmt).first()

    if inst:
        if name and (not inst.display_name or inst.display_name == inst.symbol):
            inst.display_name = name
        if exchange_val and not inst.exchange:
            inst.exchange = exchange_val
        if exchange_val and not inst.market:
            inst.market = exchange_val
        if not inst.provider_symbol:
            inst.provider_symbol = prov_sym
        # Preserve local_seed; prefer twelvedata over external_api when upgrading provider
        if inst.provider != "local_seed":
            if provider == "twelvedata":
                inst.provider = "twelvedata"
            elif provider == "external_api" and inst.provider not in ("twelvedata",):
                inst.provider = "external_api"
        db.flush()
        return inst, False

    inst = Instrument(
        symbol=symbol_norm,
        display_name=name,
        asset_class=asset_class,
        market=exchange_val,
        exchange=exchange_val,
        provider=provider,
        provider_symbol=prov_sym,
        is_active=True,
    )
    db.add(inst)
    db.flush()
    return inst, True


def fetch_twelve_and_persist_instruments(
    db: Session,
    query: str,
    *,
    asset_class: str | None,
    category: str | None,
    exchange: str | None,
    max_rows: int = 25,
    provider: str = "external_api",
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Twelve symbol_search → upsert instruments (session flush only; caller commits).

    Returns (filtered_rows, inserted_count, updated_count).
    """
    filtered = filter_twelve_instrument_search_rows(
        query,
        asset_class=asset_class,
        category=category,
        exchange=exchange,
        max_rows=max_rows,
    )
    if not filtered:
        return [], 0, 0
    ins, upd = persist_twelve_instrument_rows(db, filtered, provider=provider)
    return filtered, ins, upd
