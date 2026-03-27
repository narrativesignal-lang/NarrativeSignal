"""Schemas for Portfolio / Entity / Terms / Instrument."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

MAX_TERMS = 15


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class PortfolioOut(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class InstrumentSearchHit(BaseModel):
    id: str
    symbol: str
    display_name: str | None
    asset_class: str
    market: str | None
    exchange: str | None = None
    description: str | None = None
    country: str | None = None
    currency: str | None = None


class EntityCreate(BaseModel):
    portfolio_id: str
    name: str = Field(min_length=1, max_length=120)
    instrument_id: str | None = None
    terms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)


class EntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    instrument_id: str | None = None
    chart_layout: dict | None = None


class EntityTermOut(BaseModel):
    id: str
    term: str
    normalized_term: str
    created_at: datetime


class EntityOut(BaseModel):
    id: str
    portfolio_id: str
    name: str
    instrument_id: str | None
    instrument: InstrumentSearchHit | None
    terms: list[EntityTermOut]
    chart_layout: dict | None = None
    created_at: datetime
    updated_at: datetime


class EntityDetailOut(EntityOut):
    """Entity with portfolio name for detail/workspace view."""
    portfolio_name: str


class TermCreate(BaseModel):
    term: str = Field(min_length=1, max_length=160)


class TermOut(BaseModel):
    id: str
    term: str
    normalized_term: str
    created_at: datetime


class TermsReplace(BaseModel):
    terms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)


class RelatedInstrumentOut(BaseModel):
    """Related instrument for an entity (market data cards / comparison)."""
    id: str  # entity_related_instruments row id
    instrument_id: str  # instruments.id for comparison-series
    symbol: str
    display_name: str | None
    asset_class: str


class AddRelatedInstrumentBody(BaseModel):
    instrument_id: str


class ComparisonSeriesPoint(BaseModel):
    t: str  # iso date
    value: float  # normalized, starts at 100


class ComparisonSeriesLine(BaseModel):
    instrument_id: str
    symbol: str
    points: list[ComparisonSeriesPoint]


class ComparisonSeriesOut(BaseModel):
    period: str
    series: list[ComparisonSeriesLine]


class KeywordSuggestionRequest(BaseModel):
    idea: str = Field(min_length=1)
    instrument: str | None = None
    asset_class: str | None = None
    portfolio: str | None = None


class KeywordSuggestionResponse(BaseModel):
    keywords: list[str]


# Entity analytics: search/coverage time series and quadrant (mock or real pipeline)
class TimeSeriesPoint(BaseModel):
    t: str  # ISO date
    value: float


class TimeSeriesOut(BaseModel):
    period: str
    points: list[TimeSeriesPoint]
    data: list[TimeSeriesPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False


class QuadrantOut(BaseModel):
    search_momentum: float
    coverage_momentum: float
    last_updated_at: str | None = None
    stale: bool = False


class QuadrantHistoryPoint(BaseModel):
    t: str  # ISO date
    coverage_momentum: float
    search_momentum: float


class QuadrantHistoryOut(BaseModel):
    period: str
    points: list[QuadrantHistoryPoint]
    data: list[QuadrantHistoryPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False


class TrendingOut(BaseModel):
    """Neutral analytics summary for entity. Descriptive only, not investment advice."""
    search_momentum: float
    coverage_momentum: float
    sentiment_change: float
    trend_label: str  # Rising | Fading | Spike | Neutral
    last_updated_at: str | None = None
    stale: bool = False


class Chart3DPoint(BaseModel):
    """One day in the Narrative 3D view: time + relative trend index + coverage count."""

    date: str  # YYYY-MM-DD
    search_trend: float = Field(ge=0, le=100, description="Relative interest index 0–100, not absolute volume")
    coverage_volume: float = Field(ge=0, description="Matching news/doc count for that day (mock until indexed)")


class Chart3DSourceStatus(BaseModel):
    search_trend: str  # "mock" | "real"
    coverage_volume: str  # "mock" | "real"


class EntityChart3DDataOut(BaseModel):
    entity_id: str
    range: str  # e.g. 1m, 3m, 6m
    mode: str = "search_vs_coverage"
    points: list[Chart3DPoint]
    data: list[Chart3DPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    source_status: Chart3DSourceStatus


class SearchTrendPoint(BaseModel):
    date: str
    search_trend: float = Field(ge=0, le=100, description="Relative interest index 0–100, not absolute search volume")


class EntitySearchTrendSeriesOut(BaseModel):
    entity_id: str
    range: str
    points: list[SearchTrendPoint]
    data: list[SearchTrendPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    source_status: Chart3DSourceStatus


class EntityMetricPoint(BaseModel):
    date: str
    value: float


class EntityMetricSeriesOut(BaseModel):
    entity_id: str
    metric: str  # search_trend | coverage_volume | sentiment_score | momentum | acceleration
    range: str
    points: list[EntityMetricPoint]
