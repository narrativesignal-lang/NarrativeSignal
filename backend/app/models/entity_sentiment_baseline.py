from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntitySentimentBaseline(Base):
    """
    Cached baseline sentiment for an entity over a specific window.

    Used by AI-backed sentiment series to avoid recomputing baseline for overlapping ranges.
    """

    __tablename__ = "entity_sentiment_baselines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    window_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    window_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # exclusive
    bucket_step_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    baseline_score: Mapped[float] = mapped_column(Float, nullable=False)  # -1..+1 absolute tone
    baseline_label: Mapped[str] = mapped_column(String(16), nullable=False)  # bullish/bearish/neutral
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..100

    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_id", "window_start", "window_end", "bucket_step_days", name="uq_entity_sentiment_baseline_window"),
        Index("ix_entity_sentiment_baseline_entity_window", "entity_id", "window_start", "window_end"),
    )

