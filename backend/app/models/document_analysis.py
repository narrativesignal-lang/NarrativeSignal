from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keyword_groups.id"), index=True, nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id"), index=True, nullable=False
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="heuristic")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="v1")

    sentiment_label: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")  # bullish/bearish/neutral
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # -1..+1

    narrative_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detected_events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("group_id", "document_id", "provider", name="uq_doc_analysis_group_doc_provider"),
        Index("ix_doc_analysis_group_created", "group_id", "created_at"),
    )

