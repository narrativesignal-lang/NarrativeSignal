"""Persist and read macro news list snapshots (cache-first GET /macro/news)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.macro_news_list_snapshot import MacroNewsListSnapshot
from app.schemas.macro import MacroNewsItemOut
from app.services.macro_news import MacroNewsItem, fetch_macro_news
from app.services.macro_news_dedup import ensure_utc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MacroNewsSnapshotRead:
    """DB-backed macro news list (may be empty after subcategory filter)."""

    items: list[MacroNewsItemOut]
    updated_at_iso: str | None
    stale_age: bool
    display_source: str  # snapshot | snapshot-stale (for legacy headers)

# How many rows to store per category (superset for client subcategory filter).
SNAPSHOT_ITEM_LIMIT = 120

# After this age, response is still served from DB but marked stale (headers).
STALE_AFTER = timedelta(minutes=18)

# Categories we maintain snapshots for.
SNAPSHOT_CATEGORIES: tuple[str, ...] = ("general", "stock", "futures", "crypto")


def _item_to_row(m: MacroNewsItem) -> dict:
    return {
        "id": str(m.id),
        "title": m.title or "",
        "source": m.source or "",
        "timestamp": ensure_utc(m.timestamp).isoformat(),
        "url": m.url,
        "category": m.category or "",
        "subcategory": m.subcategory or "",
        "summary": m.summary,
        "sentiment": m.sentiment,
        "impact": float(m.impact) if m.impact is not None else None,
        "publisher_tier": int(getattr(m, "publisher_tier", 3) or 3),
        "publisher_normalized": m.publisher_normalized,
        "duplicate_count": int(getattr(m, "duplicate_count", 1) or 1),
        "related_publishers": list(m.related_publishers or [])[:5],
    }


def _row_to_out(row: dict, *, category_fallback: str) -> MacroNewsItemOut | None:
    try:
        ts_raw = row.get("timestamp")
        if not ts_raw:
            return None
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        tier = int(row.get("publisher_tier") or 3)
        tier = max(1, min(3, tier))
        dup = int(row.get("duplicate_count") or 1)
        dup = max(1, dup)
        related = [str(x) for x in (row.get("related_publishers") or []) if x is not None][:5]
        imp = row.get("impact")
        return MacroNewsItemOut(
            id=str(row.get("id") or ""),
            title=str(row.get("title") or ""),
            source=str(row.get("source") or ""),
            timestamp=ensure_utc(ts),
            url=row.get("url"),
            category=str(row.get("category") or category_fallback),
            subcategory=str(row.get("subcategory") or ""),
            summary=row.get("summary"),
            sentiment=row.get("sentiment"),
            impact=float(imp) if imp is not None else None,
            publisher_tier=tier,
            publisher_normalized=row.get("publisher_normalized"),
            duplicate_count=dup,
            related_publishers=related,
        )
    except Exception:
        logger.debug("macro news snapshot: skip bad row", exc_info=True)
        return None


def persist_snapshot_items(db: Session, category: str, items: list[MacroNewsItem]) -> None:
    cat = category.lower().strip()
    payload = [_item_to_row(m) for m in items]
    row = db.get(MacroNewsListSnapshot, cat)
    now = datetime.now(timezone.utc)
    if row is None:
        row = MacroNewsListSnapshot(category=cat, items=payload, updated_at=now)
        db.add(row)
    else:
        row.items = payload
        row.updated_at = now
        flag_modified(row, "items")

    if payload:
        try:
            from app.services.macro_news_fallback import cache_last_good_rows

            cache_last_good_rows(cat, payload, updated_at_iso=now.isoformat())
        except Exception:
            logger.debug("macro news: cache_last_good_rows after persist failed", exc_info=True)


def read_snapshot_for_request(
    db: Session,
    *,
    category: str,
    subcategory: str | None,
    limit: int,
) -> MacroNewsSnapshotRead | None:
    """
    Returns DB snapshot row data or None if there is no persisted snapshot row.
    Empty list + timestamps is valid (e.g. subcategory filter matched nothing).
    """
    cat = category.lower().strip()
    row = db.get(MacroNewsListSnapshot, cat)
    if not row or not row.items:
        return None

    raw_list = row.items
    if not isinstance(raw_list, list) or len(raw_list) == 0:
        return None

    now = datetime.now(timezone.utc)
    updated = row.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    else:
        updated = updated.astimezone(timezone.utc)
    is_stale = (now - updated) > STALE_AFTER
    updated_iso = updated.isoformat()

    outs: list[MacroNewsItemOut] = []
    for r in raw_list:
        if not isinstance(r, dict):
            continue
        o = _row_to_out(r, category_fallback=cat)
        if o:
            outs.append(o)

    if subcategory:
        outs = [x for x in outs if x.subcategory == subcategory]

    outs = outs[:limit]
    label = "snapshot-stale" if is_stale else "snapshot"
    return MacroNewsSnapshotRead(
        items=outs,
        updated_at_iso=updated_iso,
        stale_age=is_stale,
        display_source=label,
    )


def rebuild_snapshots_all_categories(db: Session) -> dict[str, int]:
    """Fetch Google News aggregate per category (no subcategory) and persist. For Celery."""
    counts: dict[str, int] = {}
    for cat in SNAPSHOT_CATEGORIES:
        try:
            items = fetch_macro_news(category=cat, subcategory=None, limit=SNAPSHOT_ITEM_LIMIT)
            persist_snapshot_items(db, cat, items)
            counts[cat] = len(items)
        except Exception:
            logger.exception("rebuild macro news snapshot failed for %s", cat)
            counts[cat] = -1
    return counts
