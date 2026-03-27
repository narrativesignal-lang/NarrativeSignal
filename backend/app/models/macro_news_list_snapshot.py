"""DB-backed cache for macro news list (Google News aggregate); refreshed by Celery, read on GET."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MacroNewsListSnapshot(Base):
    """One row per macro category slug; `items` is JSON array of news item dicts."""

    __tablename__ = "macro_news_list_snapshots"

    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    items: Mapped[list] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
