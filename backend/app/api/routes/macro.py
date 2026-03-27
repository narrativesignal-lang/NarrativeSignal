from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.macro_category import MacroCategory
from app.models.macro_event import MacroEvent
from app.models.user import User
from app.schemas.macro import MacroCategoryCreate, MacroCategoryOut, MacroEventOut, MacroNewsListResponse
from app.services.core_data_diag import (
    record_cold_empty,
    record_fallback,
    record_first_paint_envelope,
    record_snapshot_hit,
)
from app.services.macro_news_fallback import cache_last_good_from_items, resolve_macro_news_fallback
from app.services.macro_news_snapshot import read_snapshot_for_request

logger = logging.getLogger(__name__)


def _schedule_macro_news_snapshot_refresh() -> None:
    try:
        from app.worker.tasks import refresh_macro_news_list_snapshots

        refresh_macro_news_list_snapshots.apply_async(countdown=1)
    except Exception:
        logger.warning("macro news: could not schedule snapshot refresh (is Celery running?)", exc_info=True)

router = APIRouter()


@router.get("/events", response_model=list[MacroEventOut])
def list_macro_events(
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MacroEventOut]:
    stmt = select(MacroEvent).order_by(MacroEvent.timestamp.desc()).limit(limit)
    if category:
        stmt = stmt.where(MacroEvent.category == category)
    events = db.scalars(stmt).all()
    return [
        MacroEventOut(
            id=str(e.id),
            category=e.category,
            title=e.title,
            source=e.source,
            timestamp=e.timestamp,
            sentiment=e.sentiment,
            importance_score=e.importance_score,
        )
        for e in events
    ]


@router.get("/news", response_model=MacroNewsListResponse)
def list_macro_news(
    response: Response,
    category: str = Query(..., description="Macro category slug: general, stock, futures, crypto"),
    subcategory: str | None = Query(default=None, description="Optional subcategory name, e.g. Semiconductors"),
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MacroNewsListResponse:
    """
    Macro news: **DB snapshot only** on the request path. No live RSS/Google fetch in-process.

    - Reads `macro_news_list_snapshots`; subcategory slices return rows or, when the snapshot row is missing,
      Redis last-good rows, then deterministic demo headlines — never a silent empty list without status fields.
    - If snapshot age exceeds the freshness window, still returns rows, marks stale, and schedules async rebuild.
    """
    cat = category.lower()
    if cat not in {"general", "stock", "futures", "crypto"}:
        raise HTTPException(status_code=400, detail="Unsupported macro category")

    snap = read_snapshot_for_request(db, category=cat, subcategory=subcategory, limit=limit)
    if snap is not None:
        record_snapshot_hit("macro_news")
        if snap.items:
            try:
                cache_last_good_from_items(cat, snap.items, updated_at_iso=snap.updated_at_iso)
            except Exception:
                logger.debug("macro news: cache_last_good_from_items failed", exc_info=True)
        response.headers["X-Macro-News-Source"] = snap.display_source
        if snap.stale_age:
            response.headers["X-Macro-News-Stale"] = "true"
        ds: str = "stale_fallback" if snap.stale_age else "snapshot"
        ls = "stale" if snap.stale_age else "ready"
        if snap.stale_age:
            _schedule_macro_news_snapshot_refresh()
        record_first_paint_envelope("macro_news", loading_state=ls, data_source=ds)
        return MacroNewsListResponse(
            data=snap.items,
            data_updated_at=snap.updated_at_iso,
            data_source=ds,
            stale=snap.stale_age,
            loading_state=ls,
            message=None,
        )

    record_fallback("macro_news_no_snapshot")
    response.headers["X-Macro-News-Source"] = "pending-refresh"
    response.headers["X-Macro-News-Stale"] = "true"
    _schedule_macro_news_snapshot_refresh()
    items, lu, ds, ls, msg = resolve_macro_news_fallback(cat, subcategory, limit)
    if not items:
        record_cold_empty("macro_news")
        record_first_paint_envelope("macro_news", loading_state="warming", data_source="placeholder")
        return MacroNewsListResponse(
            data=[],
            data_updated_at=None,
            data_source="placeholder",
            stale=True,
            loading_state="warming",
            message=msg or "Macro news snapshots are preparing; retry in a few seconds.",
        )
    record_first_paint_envelope("macro_news", loading_state=ls, data_source=ds)
    return MacroNewsListResponse(
        data=items,
        data_updated_at=lu,
        data_source=ds,
        stale=True,
        loading_state=ls,
        message=msg,
    )


@router.get("/categories", response_model=list[MacroCategoryOut])
def list_macro_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MacroCategoryOut]:
    rows = db.scalars(
        select(MacroCategory)
        .where(MacroCategory.user_id == current_user.id)
        .order_by(MacroCategory.created_at.asc())
    ).all()
    return [
        MacroCategoryOut(id=str(r.id), name=r.name, created_at=r.created_at)
        for r in rows
    ]


@router.post("/categories", response_model=MacroCategoryOut, status_code=status.HTTP_201_CREATED)
def create_macro_category(
    payload: MacroCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MacroCategoryOut:
    cat = MacroCategory(user_id=current_user.id, name=payload.name.strip())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return MacroCategoryOut(id=str(cat.id), name=cat.name, created_at=cat.created_at)


@router.delete("/categories/{category_id}", status_code=status.HTTP_200_OK)
def delete_macro_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    cid = uuid.UUID(category_id)
    cat = db.scalar(
        select(MacroCategory).where(
            MacroCategory.id == cid,
            MacroCategory.user_id == current_user.id,
        )
    )
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(cat)
    db.commit()
    return {"ok": True}
