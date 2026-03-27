from __future__ import annotations

from pydantic import BaseModel, Field


class EntityConfigOut(BaseModel):
    group_id: str
    config: dict


class EntityConfigUpdate(BaseModel):
    config: dict = Field(default_factory=dict)
