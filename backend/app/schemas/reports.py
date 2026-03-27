from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReportOut(BaseModel):
    id: str
    kind: str
    title: str
    label: str | None = None
    schedule_type: str | None = None
    body_markdown: str
    window_start: datetime | None
    window_end: datetime | None
    created_at: datetime



