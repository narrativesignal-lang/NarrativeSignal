from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MacroEventOut(BaseModel):
    id: str
    category: str
    title: str
    source: str
    timestamp: datetime
    sentiment: str | None
    importance_score: float | None


class MacroCategoryOut(BaseModel):
    id: str
    name: str
    created_at: datetime


class MacroCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class MacroNewsItemOut(BaseModel):
    id: str
    title: str
    source: str
    timestamp: datetime
    url: str | None
    category: str
    subcategory: str
    summary: str | None = None
    sentiment: str | None = None
    impact: float | None = None
    publisher_tier: int = Field(default=3, ge=1, le=3)
    publisher_normalized: str | None = None
    duplicate_count: int = Field(default=1, ge=1)
    related_publishers: list[str] = Field(default_factory=list, max_length=5)


class MacroNewsListResponse(BaseModel):
    """Envelope for GET /macro/news (snapshot-first; never blocks on live RSS in-request)."""

    data: list[MacroNewsItemOut]
    data_updated_at: str | None = None
    data_source: Literal["snapshot", "stale_fallback", "placeholder", "cache", "external"] = "snapshot"
    stale: bool = False
    loading_state: Literal["ready", "warming", "placeholder", "stale"] = "ready"
    message: str | None = None

