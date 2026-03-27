from __future__ import annotations

from datetime import datetime

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

