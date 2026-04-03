from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntityAnalysis(Base):
    """
    Massive isolated analysis outputs (non-display path).
    Must not be written into price/snapshot/chart tables.
    """

    __tablename__ = "entity_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    narrative_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_analysis_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    analysis_source: Mapped[str] = mapped_column(String(40), nullable=False, default="massive_light")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("entity_id", name="uq_entity_analysis_entity"),)
