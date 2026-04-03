from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.limits import MAX_REPORTS
from app.db.session import get_db
from app.models.report import Report
from app.models.user import User
from app.schemas.reports import ReportOut


router = APIRouter()


@router.get("", response_model=list[ReportOut])
def list_reports(
    kind: str | None = Query(default=None),
    label: str | None = Query(default=None),
    schedule_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportOut]:
    try:
        stmt = select(Report).where(Report.user_id == current_user.id)
        if kind:
            stmt = stmt.where(Report.kind == kind)
        if label:
            stmt = stmt.where(Report.label == label)
        if schedule_type:
            stmt = stmt.where(Report.schedule_type == schedule_type)
        reports = db.scalars(stmt.order_by(Report.created_at.desc()).limit(limit)).all()
    except Exception:
        # Prefer an honest empty state over a 500 that breaks the whole page.
        return []
    return [
        ReportOut(
            id=str(r.id),
            kind=r.kind,
            title=r.title,
            label=getattr(r, "label", None),
            schedule_type=getattr(r, "schedule_type", None),
            body_markdown=r.body_markdown,
            window_start=r.window_start,
            window_end=r.window_end,
            created_at=r.created_at,
        )
        for r in reports
    ]


@router.delete("", status_code=status.HTTP_200_OK)
def delete_reports(
    ids: list[str] = Body(..., embed=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not ids:
        return {"deleted": 0}
    uuids = []
    for x in ids:
        try:
            uuids.append(uuid.UUID(x))
        except ValueError:
            continue
    db.execute(delete(Report).where(Report.user_id == current_user.id, Report.id.in_(uuids)))
    db.commit()
    return {"deleted": len(uuids)}


@router.get("/count")
def get_report_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return total report count for current user (for limit messaging)."""
    n = db.scalar(select(func.count()).select_from(Report).where(Report.user_id == current_user.id))
    return {"count": n or 0, "max": MAX_REPORTS, "at_limit": (n or 0) >= MAX_REPORTS}

