"""Community submissions and data requests. Scaffolding for future paid/token features."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommunitySubmission(Base):
    """General community submission (tools, indicators, workflows, ideas)."""

    __tablename__ = "community_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)

    category: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    problem_solves: Mapped[str] = mapped_column(Text, nullable=False, default="")
    platform_data_used: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_data_source: Mapped[bool] = mapped_column(nullable=False, default=False)
    data_source_access: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact_info: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CommunityDataRequest(Base):
    """Data request submissions."""

    __tablename__ = "community_data_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)

    requested_data_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    use_case: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_known: Mapped[bool] = mapped_column(nullable=False, default=False)
    how_to_obtain: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact_info: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
