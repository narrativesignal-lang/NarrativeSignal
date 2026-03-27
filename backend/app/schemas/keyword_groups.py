from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KeywordTermIn(BaseModel):
    term: str = Field(min_length=1, max_length=160)
    is_required: bool = False


class KeywordTermOut(KeywordTermIn):
    id: str


class KeywordGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    terms: list[KeywordTermIn] = Field(default_factory=list)


class KeywordGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    is_active: bool | None = None
    terms: list[KeywordTermIn] | None = None


class KeywordGroupOut(BaseModel):
    id: str
    name: str
    description: str | None
    is_active: bool
    terms: list[KeywordTermOut]
    created_at: datetime
    updated_at: datetime

