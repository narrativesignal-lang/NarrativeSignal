from __future__ import annotations

from pydantic import BaseModel, Field


class GroupAssetUpsert(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    provider: str = Field(default="stooq", max_length=40)


class GroupAssetOut(BaseModel):
    group_id: str
    symbol: str
    provider: str

