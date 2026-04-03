from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemRuntimeFlag(Base):
    __tablename__ = "system_runtime_flags"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_bool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)

