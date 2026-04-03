"""API contracts for entity price-chart event/news timeline (premium-ready)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TimelineAccessOut(BaseModel):
    can_interact: bool
    is_admin: bool
    paid_access: bool = False
    credits_balance: int = 0
    reason: str | None = Field(
        default=None,
        description="admin | paid_and_credited | need_paid_or_topup — why can_interact is true/false",
    )


class TimelinePointOut(BaseModel):
    id: str
    point_type: Literal["volatility", "official"]
    time: int = Field(description="Unix seconds; aligns with OHLCV bar times")
    score: float | None = Field(default=None, description="volatility rank metric when type=volatility")
    label_hint: str | None = None


class TimelinePointsResponse(BaseModel):
    access: TimelineAccessOut
    symbol: str
    period: str
    chart_scope: str
    range_start: int
    range_end: int
    points: list[TimelinePointOut]
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    stale: bool = False
    official_events_available: bool = Field(
        default=False,
        description="True when structured official/scheduled events are ingested (e.g. SEC, economic calendar).",
    )


class TimelineNewsItemOut(BaseModel):
    id: str
    title: str
    source_name: str
    source_url: str | None = None
    summary: str
    sentiment: Literal["bullish", "bearish", "neutral"] = "neutral"
    category: str = "general"


class TimelineWindowResponse(BaseModel):
    point_id: str
    point_type: Literal["volatility", "official"]
    focus_time: int
    window_start_iso: str
    window_end_iso: str
    symbol: str
    items: list[TimelineNewsItemOut]
    data_mode: Literal["placeholder", "live"] = "live"
    news_status: Literal["has_items", "no_relevant_news", "fetch_failed"] = "has_items"
    status_message: str | None = Field(
        default=None,
        description="Human-facing note when items are empty (e.g. no relevant news for a volatility move).",
    )


class AiSummaryRequest(BaseModel):
    point_id: str = Field(..., min_length=3, max_length=256)
    provider: Literal["gemini", "openai", "anthropic", "qwen"] = "gemini"
    summary_window: Literal["point", "24h", "72h", "7d", "custom"] = "point"
    custom_start_iso: str | None = Field(default=None, max_length=80)
    custom_end_iso: str | None = Field(default=None, max_length=80)


class AiCitationOut(BaseModel):
    title: str
    url: str | None = None


class AiSummaryResponse(BaseModel):
    status: Literal["placeholder", "ok", "error"] = "placeholder"
    provider: str
    interpretation: Literal["bullish", "bearish", "mixed", "neutral"] | None = None
    summary: str
    citations: list[AiCitationOut] = Field(default_factory=list)
    model_label: str | None = None
    detail: str | None = Field(default=None, description="Error or not-implemented note")
