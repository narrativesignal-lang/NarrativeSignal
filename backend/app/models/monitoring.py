from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


SCHEDULE_TYPES = ("standard_monitor", "ai_alert", "ai_report", "general_alert")
MODEL_OPTIONS = ("gemini", "gpt", "claude", "grok", "qwen")


class MonitoringSchedule(Base):
    __tablename__ = "monitoring_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cron: Mapped[str] = mapped_column(String(80), nullable=False)  # standard 5-field cron
    # Legacy flag kept for compatibility; status is the primary state.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active / paused

    schedule_type: Mapped[str] = mapped_column(String(40), nullable=False, default="standard_monitor")
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)  # user-defined label
    model: Mapped[str | None] = mapped_column(String(40), nullable=True)  # gemini/gpt/claude/grok/qwen
    impact_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100, trigger threshold
    linked_assets_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")  # optional symbols

    group_ids_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")  # legacy keyword groups
    entity_ids_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")  # new: portfolio entity ids
    bucket_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    runs: Mapped[list["MonitoringRun"]] = relationship(
        "MonitoringRun",
        back_populates="schedule",
        foreign_keys="MonitoringRun.schedule_id",
        cascade="all, delete",
    )

    __table_args__ = (Index("ix_monitoring_schedules_user_active", "user_id", "is_active"),)


class TriggeredAlert(Base):
    __tablename__ = "triggered_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_schedules.id"), nullable=True
    )
    schedule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    impact_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_schedules.id"), index=True, nullable=True
    )

    schedule: Mapped["MonitoringSchedule | None"] = relationship(
        "MonitoringSchedule", back_populates="runs", foreign_keys=[schedule_id]
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")  # queued/running/success/fail
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

