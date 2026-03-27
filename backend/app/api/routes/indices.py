from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.indices import IndexPointOut, IndexSeriesResponse
from app.services.narrative_metrics import fetch_keyword_group_index_points


router = APIRouter()


@router.get("/series/{group_id}", response_model=IndexSeriesResponse)
def get_series(
    group_id: str,
    hours: int = Query(72, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IndexSeriesResponse:
    gid = uuid.UUID(group_id)
    points = fetch_keyword_group_index_points(db, current_user.id, gid, hours)
    if not points:
        return IndexSeriesResponse(group_id=group_id, points=[])

    return IndexSeriesResponse(
        group_id=group_id,
        points=[
            IndexPointOut(
                bucket_start=p.bucket_start,
                bucket_minutes=p.bucket_minutes,
                mention_volume=p.mention_volume,
                sentiment_positive=p.sentiment_positive,
                sentiment_negative=p.sentiment_negative,
                sentiment_neutral=p.sentiment_neutral,
                momentum=p.momentum,
                d1=p.d1,
                d2=p.d2,
            )
            for p in points
        ],
    )

