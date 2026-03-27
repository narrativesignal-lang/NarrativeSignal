from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.macro_category import MacroCategory
from app.models.macro_event import MacroEvent
from app.models.user import User
from app.schemas.macro import MacroCategoryCreate, MacroCategoryOut, MacroEventOut, MacroNewsItemOut
from app.services.macro_news import fetch_macro_news

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


@router.get("/news", response_model=list[MacroNewsItemOut])
def list_macro_news(
    category: str = Query(..., description="Macro category slug: general, stock, futures, crypto"),
    subcategory: str | None = Query(default=None, description="Optional subcategory name, e.g. Semiconductors"),
    limit: int = Query(default=40, ge=1, le=200),
    current_user: User = Depends(get_current_user),  # kept for auth consistency
) -> list[MacroNewsItemOut]:
    """
    Aggregated macro news for the Macro Data tab.

    - Uses RSS / Google News feeds per category/subcategory mapping.
    - Returns normalized news items: title, source, timestamp, url, category, subcategory.
    - Does not persist to the database; uses an in-process cache with short TTL.
    """
    # Normalize category input defensively
    cat = category.lower()
    if cat not in {"general", "stock", "futures", "crypto"}:
        raise HTTPException(status_code=400, detail="Unsupported macro category")

    items = fetch_macro_news(category=cat, subcategory=subcategory, limit=limit)
    return [
        MacroNewsItemOut(
            id=i.id,
            title=i.title,
            source=i.source,
            timestamp=i.timestamp,
            url=i.url,
            category=i.category,
            subcategory=i.subcategory,
            summary=i.summary,
            sentiment=i.sentiment,
            impact=i.impact,
        )
        for i in items
    ]


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
