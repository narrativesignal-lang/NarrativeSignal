from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AiDisabledResponse(BaseModel):
    ok: bool = False
    disabled: bool = True
    reason: str = "disabled_by_runtime_flag"


class EntityChartWindowRequest(BaseModel):
    """User-selected chart window (UTC instants)."""

    entity_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    chart_period: str = Field(default="1M", max_length=16, description="OHLCV snapshot period key (e.g. 1M).")

    @field_validator("chart_period")
    @classmethod
    def strip_period(cls, v: str) -> str:
        return (v or "1M").strip() or "1M"


class PriceMoveDriver(BaseModel):
    label: str = Field(..., max_length=400)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_type: str = Field(..., description="news|coverage|search|price")

    @field_validator("evidence_type")
    @classmethod
    def evidence_ok(cls, v: str) -> str:
        allowed = frozenset({"news", "coverage", "search", "price"})
        low = (v or "").strip().lower()
        if low not in allowed:
            return "price"
        return low


class PriceMoveExplanationOut(BaseModel):
    summary: str = Field(..., description="Short neutral explanation; no trade advice.")
    drivers: list[PriceMoveDriver] = Field(default_factory=list)
    time_window_start: datetime
    time_window_end: datetime
    cached: bool = False


class RangeSummaryOut(BaseModel):
    summary: str = Field(..., description="Structured-style headline summary.")
    narrative: str = Field(..., description="Short neutral narrative; no trade advice.")
    highlights: list[str] = Field(default_factory=list, description="Short factual bullets from stored data.")
    time_window_start: datetime
    time_window_end: datetime
    cached: bool = False


class CompareSummaryOut(BaseModel):
    entities: list[str] = Field(default_factory=list, description="Entity identifiers/symbols referenced in this comparison.")
    differences: list[str] = Field(default_factory=list, description="Short bullet-like difference statements.")
    common_drivers: list[str] = Field(default_factory=list, description="Shared driver phrases across compared entities.")
