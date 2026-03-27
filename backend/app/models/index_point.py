from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IndexPoint(Base):
    __tablename__ = "index_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keyword_groups.id"), index=True, nullable=False
    )

    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    bucket_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    mention_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentiment_positive: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentiment_negative: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentiment_neutral: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    momentum: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    d1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    d2: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    method_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_index_points_group_bucket", "group_id", "bucket_start", unique=True),
    )

