"""Triggered AI alerts - list only (MVP)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.monitoring import TriggeredAlert
from app.models.user import User
from app.schemas.alerts import AlertOut


router = APIRouter()


@router.get("", response_model=list[AlertOut])
def list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertOut]:
    rows = db.scalars(
        select(TriggeredAlert)
        .where(TriggeredAlert.user_id == current_user.id)
        .order_by(TriggeredAlert.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AlertOut(
            id=str(r.id),
            schedule_id=str(r.schedule_id) if r.schedule_id else None,
            schedule_type=r.schedule_type,
            title=r.title,
            body_markdown=r.body_markdown or "",
            impact_score=r.impact_score,
            payload=r.payload or {},
            created_at=r.created_at,
        )
        for r in rows
    ]
