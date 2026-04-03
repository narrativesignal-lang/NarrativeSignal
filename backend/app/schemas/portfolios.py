"""Schemas for Portfolio / Entity / Terms / Instrument."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    # local_db: persisted instruments; external_fallback: Twelve-only (e.g. DB persist failed or incomplete)
    data_origin: Literal["local_db", "external_fallback"] = "local_db"


class InstrumentBindResolve(BaseModel):
    """Identity to persist an instrument when search returned an ephemeral id (ext-pending-*)."""

    symbol: str = Field(min_length=1, max_length=60)
    asset_class: str = Field(min_length=1, max_length=40)
    exchange: str | None = Field(default=None, max_length=60)
    display_name: str | None = Field(default=None, max_length=120)


class EntityCreate(BaseModel):
    portfolio_id: str
    name: str = Field(min_length=1, max_length=120)
    instrument_id: str | None = None
    instrument_resolve: InstrumentBindResolve | None = None
    terms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)


class EntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    instrument_id: str | None = None
    instrument_resolve: InstrumentBindResolve | None = None
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
    instrument_resolve: InstrumentBindResolve | None = None


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
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    stale: bool = False


class KeywordSuggestionRequest(BaseModel):
    idea: str = Field(min_length=1)
    instrument: str | None = None
    asset_class: str | None = None
    portfolio: str | None = None


class KeywordSuggestionResponse(BaseModel):
    keywords: list[str]
    ok: bool | None = None
    disabled: bool | None = None
    reason: str | None = None


# Entity analytics: search/coverage time series and quadrant
class TimeSeriesPoint(BaseModel):
    t: str  # ISO date
    value: float


class TimeSeriesOut(BaseModel):
    period: str
    points: list[TimeSeriesPoint]
    data: list[TimeSeriesPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["ready", "warming", "placeholder", "stale", "no_data"] = "ready"
    message: str | None = None


# --- AI-backed sentiment series (delta vs baseline) ---
class SentimentSeriesPoint(BaseModel):
    t: str  # ISO date (bucket end, YYYY-MM-DD)
    sentiment_score: float = Field(ge=-1, le=1, description="Delta vs baseline in [-1, +1]")
    sentiment_label: Literal["bullish", "bearish", "neutral"]
    confidence: float | None = Field(default=None, ge=0, le=100)


class SentimentSeriesOut(BaseModel):
    period: str
    points: list[SentimentSeriesPoint]
    data: list[SentimentSeriesPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["complete", "partial", "computing", "disabled"] = "complete"
    message: str | None = None
    eta_hint: str | None = None


class QuadrantOut(BaseModel):
    keywords_search_volume: float
    coverage_volume: float
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["ready", "warming", "placeholder", "stale"] = "ready"
    message: str | None = None


class QuadrantHistoryPoint(BaseModel):
    t: str  # ISO date
    coverage_volume: float
    keywords_search_volume: float


class QuadrantHistoryOut(BaseModel):
    period: str
    points: list[QuadrantHistoryPoint]
    data: list[QuadrantHistoryPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["ready", "warming", "placeholder", "stale"] = "ready"
    message: str | None = None


class TrendingOut(BaseModel):
    """Neutral analytics summary for entity. Descriptive only, not investment advice."""
    search_momentum: float
    coverage_momentum: float
    sentiment_change: float
    trend_label: str  # Rising | Fading | Spike | Neutral
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["ready", "warming", "placeholder", "stale"] = "ready"
    message: str | None = None


class InstitutionBiasOut(BaseModel):
    """DB-only heuristic bias proxy (non-AI)."""

    bias_label: str  # Bullish | Neutral | Bearish
    score: float = Field(ge=0, le=100)
    bullish_pct: float = Field(ge=0, le=100)
    neutral_pct: float = Field(ge=0, le=100)
    bearish_pct: float = Field(ge=0, le=100)
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["ready", "warming", "placeholder", "stale"] = "ready"
    message: str | None = None


class RatingDistributionOut(BaseModel):
    """DB-only heuristic rating mix proxy (non-AI)."""

    buy_pct: float = Field(ge=0, le=100)
    hold_pct: float = Field(ge=0, le=100)
    sell_pct: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=100, description="Heuristic confidence (data availability proxy)")
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    loading_state: Literal["ready", "warming", "placeholder", "stale"] = "ready"
    message: str | None = None


class Chart3DPoint(BaseModel):
    """One day in the Narrative 3D view: narrative keyword search index + coverage count."""

    date: str  # YYYY-MM-DD
    keywords_search_volume: float = Field(
        ge=0, description="Sum of independent narrative keyword Trends indices for that day (not target/ticker)."
    )
    coverage_volume: float = Field(ge=0, description="Matching news/doc count for that day")


class Chart3DSourceStatus(BaseModel):
    keywords_search_volume: str = "n/a"  # real | unavailable | n/a
    coverage_volume: str = "n/a"
    target_search_volume: str = "n/a"


class EntityChart3DDataOut(BaseModel):
    entity_id: str
    range: str  # e.g. 1m, 3m, 6m
    mode: str = "search_vs_coverage"
    points: list[Chart3DPoint]
    data: list[Chart3DPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    source_status: Chart3DSourceStatus
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    message: str | None = None


class KeywordsSearchPoint(BaseModel):
    date: str
    keywords_search_volume: float = Field(ge=0, description="Narrative keyword Trends aggregate for that day")


class TargetSearchPoint(BaseModel):
    date: str
    target_search_volume: float = Field(ge=0, description="Primary instrument symbol Trends index for that day")


class EntityKeywordsSearchSeriesOut(BaseModel):
    entity_id: str
    range: str
    points: list[KeywordsSearchPoint]
    data: list[KeywordsSearchPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    source_status: Chart3DSourceStatus
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    message: str | None = None


class EntityTargetSearchSeriesOut(BaseModel):
    entity_id: str
    range: str
    points: list[TargetSearchPoint]
    data: list[TargetSearchPoint] | None = None
    last_updated_at: str | None = None
    stale: bool = False
    source_status: Chart3DSourceStatus
    data_updated_at: str | None = None
    data_source: str = "snapshot"
    message: str | None = None


class EntityMetricPoint(BaseModel):
    date: str
    value: float


class EntityMetricSeriesOut(BaseModel):
    entity_id: str
    metric: str  # target_search_volume | keywords_search_volume | coverage_volume | sentiment_score | momentum_* | acceleration_*
    range: str
    points: list[EntityMetricPoint]


class TripleSignalSeriesOut(BaseModel):
    period: str
    axis: list[str]
    trading_activity: list[float | None]
    news_volume: list[float | None]
    search_volume: list[float | None]
    last_updated_at: str | None = None
    stale: bool = False
    data_updated_at: str | None = None
    data_source: str = "snapshot"


class EntityNewsItemOut(BaseModel):
    title: str
    source: str
    published_at: str | None = None
    url: str | None = None
    snippet: str | None = None
    matched_by: Literal["target", "keyword"] | None = None


class EntityNewsOut(BaseModel):
    mode: str
    query: str | None = None
    items: list[EntityNewsItemOut]
    cached: bool = False
    error: str | None = None  # no_keywords | fetch_failed | optional diagnostic
