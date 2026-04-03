"""Unified subscriptions + local caches for the data pipeline (no direct external hits from UI)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserDataSubscription(Base):
    """
    Declares what data to refresh for a user-owned object.
    Dedup: (user_id, source_type, target_type, target_id).
    """

    __tablename__ = "user_data_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # market_quote | search_trend | news_coverage | news_feed | entity_news
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # instrument | entity | keyword_group | macro_category
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")
    # 15m | daily | manual_refresh
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "target_type", "target_id", name="uq_user_data_subscription_scope"),
        Index("ix_subs_active_freq", "is_active", "frequency"),
    )


class MarketQuoteSnapshot(Base):
    """Latest successful quote per symbol (shared cache for watchlist + cards)."""

    __tablename__ = "market_quote_snapshots"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class OhlcvSnapshot(Base):
    """Latest successful OHLCV snapshot per (symbol, period)."""

    __tablename__ = "ohlcv_snapshots"

    snapshot_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    bars: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class EntityDailyMetric(Base):
    """Per-entity daily metrics: target vs narrative Google Trends (0–100 each), coverage, sentiment."""

    __tablename__ = "entity_daily_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Legacy mixed column — no longer written by sync; use target/keywords columns.
    search_trend: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_search_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    keywords_search_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_trend_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # legacy
    target_search_volume_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    keywords_search_volume_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    coverage_volume_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("entity_id", "metric_date", name="uq_entity_daily_metric_day"),)


class EntityTripleSignalDaily(Base):
    """Precomputed non-AI triple signals (normalized 0-100) per entity/day."""

    __tablename__ = "entity_triple_signal_daily"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    trading_activity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    news_volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    search_volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("entity_id", "metric_date", name="uq_entity_triple_signal_day"),)


class NormalizedNewsDocument(Base):
    """
    Cross-source normalized article row for dedup + coverage.
    Google / Google News slots use source_channel placeholder until wired.
    """

    __tablename__ = "normalized_news_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    title_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # rss | google_search | google_news | other
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id", ondelete="SET NULL"), index=True, nullable=True
    )
    keyword_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keyword_groups.id", ondelete="SET NULL"), index=True, nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dedup_cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True, nullable=True)
    raw_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_norm_news_entity_pub", "entity_id", "published_at"),)
