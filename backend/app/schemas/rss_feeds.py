from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RssFeedCreate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    url: str = Field(min_length=5)
    is_active: bool = True


class RssFeedOut(BaseModel):
    id: str
    name: str | None
    url: str
    is_active: bool
    created_at: datetime

