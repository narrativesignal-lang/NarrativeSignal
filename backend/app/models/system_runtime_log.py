from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemRuntimeLog(Base):
    __tablename__ = "system_runtime_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    category: Mapped[str] = mapped_column(String(24), nullable=False, default="system")

    job_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # success/skipped/failed/paused

    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    disabled_by_runtime_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    no_provider_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    request_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

