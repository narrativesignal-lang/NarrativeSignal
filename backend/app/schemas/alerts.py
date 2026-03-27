from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AlertOut(BaseModel):
    id: str
    schedule_id: str | None
    schedule_type: str
    title: str
    body_markdown: str
    impact_score: int | None
    payload: dict
    created_at: datetime
