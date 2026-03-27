from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# Research project layout_config may contain entity-based chart references (migration from keyword groups).
# Example layout_config: { "charts": [{ "entity_id": "uuid", "chart_type": "price"|"sentiment"|..., "market_item": "optional" }] }
class ResearchChartItem(BaseModel):
    """Optional shape for layout_config.charts[] when using Entity-based charts."""
    entity_id: str | None = None
    chart_type: str | None = None  # price, search_volume, coverage_volume, sentiment, quadrant, etc.
    market_item: str | None = None  # optional macro/market reference


class ResearchFolderOut(BaseModel):
    id: str
    name: str
    parent_id: str | None
    created_at: datetime


class ResearchFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


class ResearchFolderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    parent_id: str | None = None


class ResearchProjectOut(BaseModel):
    id: str
    folder_id: str
    name: str
    layout_type: str
    layout_config: dict  # may include "charts": [{"entity_id", "chart_type", "market_item"?}]
    created_at: datetime


class ResearchProjectCreate(BaseModel):
    folder_id: str
    name: str = Field(min_length=1, max_length=120)
    layout_type: str = Field(default="single", pattern="^(single|split|overlay)$")


class ResearchProjectUpdate(BaseModel):
    folder_id: str | None = None
    name: str | None = Field(None, min_length=1, max_length=120)
    layout_type: str | None = Field(None, pattern="^(single|split|overlay)$")
    layout_config: dict | None = None


class ResearchSetupSnapshotSave(BaseModel):
    """Payload to save current tab as a snapshot; returns share code."""
    config: dict = Field(default_factory=dict)
    name: str | None = Field(None, max_length=120)


class ResearchSetupSnapshotOut(BaseModel):
    """Response after saving: share code and optional name."""
    code: str
    name: str | None = None


class ResearchSetupSnapshotListItem(BaseModel):
    """One saved setup in list (for management UI)."""
    code: str
    name: str | None
    created_at: datetime


class ResearchSetupSnapshotUpdate(BaseModel):
    """Rename a saved setup."""
    name: str | None = Field(None, max_length=120)


class ResearchSetupSnapshotImportOut(BaseModel):
    """Response when importing by code: full config (snapshot, not live tab)."""
    config: dict
