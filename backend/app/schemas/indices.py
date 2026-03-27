from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IndexPointOut(BaseModel):
    bucket_start: datetime
    bucket_minutes: int
    mention_volume: int
    sentiment_positive: int
    sentiment_negative: int
    sentiment_neutral: int
    momentum: float
    d1: float
    d2: float


class IndexSeriesResponse(BaseModel):
    group_id: str
    points: list[IndexPointOut]

