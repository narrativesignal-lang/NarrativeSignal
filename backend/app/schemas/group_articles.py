from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GroupArticleOut(BaseModel):
    document_id: str
    title: str | None
    url: str | None
    source: str
    published_at: datetime | None
    content: str | None
    metadata: dict

    sentiment_label: str | None
    sentiment_score: float | None
    narrative_summary: str | None
    detected_events: list | None


class GroupArticlesResponse(BaseModel):
    group_id: str
    items: list[GroupArticleOut]

