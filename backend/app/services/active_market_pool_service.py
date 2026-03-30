"""Global active pool: add/touch Twelve-eligible symbols; stale disable; list for Celery refresh."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.active_market_pool import ActiveMarketPoolEntry
from app.services.cache_fallback import utcnow
from app.services.market_provider_router import route_quote_provider
from app.services.symbol_mapping import map_symbol_for_twelve, normalize_user_symbol
from app.services.twelve_warm_pool import TWELVE_WARM_POOL_SYMBOLS

logger = logging.getLogger(__name__)

ACTIVE_POOL_SOURCE_TYPE = "active_pool"
# Max concurrently enabled symbols (new adds rejected when at cap; touches always allowed).
ACTIVE_POOL_MAX_ENABLED = 200
ACTIVE_POOL_STALE_DAYS = 7

_WARM_SYMBOLS_UPPER = frozenset(s.strip().upper() for s in TWELVE_WARM_POOL_SYMBOLS)


def record_active_pool_interaction(db: Session, symbol: str) -> None:
    """
    Add or touch an active_pool row if symbol maps for Twelve after normalization.
    Call from entity–instrument bind and after successful Twelve market API hits.
    """
    raw = symbol or ""
    norm = normalize_user_symbol(symbol)
    if not norm:
        return
    if raw.strip() != norm:
        logger.info("symbol_normalized from=%s to=%s", raw, norm)
    if route_quote_provider(raw) != "twelvedata":
        logger.info("active_pool skip symbol=%s reason=unsupported", norm)
        return
    mapped = map_symbol_for_twelve(norm)
    if mapped is None:
        logger.info("active_pool skip symbol=%s reason=unsupported", norm)
        return
    if mapped != norm:
        logger.info("symbol_mapped provider=twelve from=%s to=%s", norm, mapped)
    sym = mapped

    now = utcnow()
    row = db.scalar(
        select(ActiveMarketPoolEntry).where(
            ActiveMarketPoolEntry.symbol == sym,
            ActiveMarketPoolEntry.source_type == ACTIVE_POOL_SOURCE_TYPE,
        )
    )
    if row:
        row.last_accessed_at = now
        if not row.is_enabled:
            row.is_enabled = True
        logger.info("active_pool touch symbol=%s", sym)
        return

    n_enabled = db.scalar(
        select(func.count())
        .select_from(ActiveMarketPoolEntry)
        .where(
            ActiveMarketPoolEntry.is_enabled.is_(True),
            ActiveMarketPoolEntry.source_type == ACTIVE_POOL_SOURCE_TYPE,
        )
    )
    if (n_enabled or 0) >= ACTIVE_POOL_MAX_ENABLED:
        logger.info("active_pool skip symbol=%s reason=pool_full", sym)
        return

    try:
        with db.begin_nested():
            db.add(
                ActiveMarketPoolEntry(
                    symbol=sym,
                    source_type=ACTIVE_POOL_SOURCE_TYPE,
                    last_accessed_at=now,
                    is_enabled=True,
                )
            )
            db.flush()
    except IntegrityError:
        existed = db.scalar(
            select(ActiveMarketPoolEntry).where(
                ActiveMarketPoolEntry.symbol == sym,
                ActiveMarketPoolEntry.source_type == ACTIVE_POOL_SOURCE_TYPE,
            )
        )
        if existed:
            existed.last_accessed_at = now
            existed.is_enabled = True
            logger.info("active_pool skip symbol=%s reason=duplicate", sym)
            logger.info("active_pool touch symbol=%s", sym)
        else:
            logger.warning("active_pool IntegrityError missing row symbol=%s", sym)
        return

    logger.info("active_pool add symbol=%s", sym)


def disable_stale_active_pool_entries(db: Session) -> int:
    """
    Disable rows whose last activity (last_accessed_at or created_at) is older than ACTIVE_POOL_STALE_DAYS.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_POOL_STALE_DAYS)
    stmt = select(ActiveMarketPoolEntry).where(
        ActiveMarketPoolEntry.is_enabled.is_(True),
        ActiveMarketPoolEntry.source_type == ACTIVE_POOL_SOURCE_TYPE,
        func.coalesce(ActiveMarketPoolEntry.last_accessed_at, ActiveMarketPoolEntry.created_at) < cutoff,
    )
    rows = list(db.scalars(stmt).all())
    for r in rows:
        r.is_enabled = False
        logger.info("active_pool disable stale symbol=%s", r.symbol)
    return len(rows)


def list_enabled_active_pool_symbols_excluding_warm(db: Session) -> list[str]:
    """Symbols to refresh: enabled active_pool only, excluding fixed warm pool (separate Celery tasks)."""
    rows = db.scalars(
        select(ActiveMarketPoolEntry.symbol).where(
            ActiveMarketPoolEntry.is_enabled.is_(True),
            ActiveMarketPoolEntry.source_type == ACTIVE_POOL_SOURCE_TYPE,
        )
    ).all()
    out = {str(s).strip().upper() for s in rows if s}
    out -= _WARM_SYMBOLS_UPPER
    return sorted(out)
