from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KeywordGroup(Base):
    __tablename__ = "keyword_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    terms: Mapped[list["KeywordTerm"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_keyword_groups_user_name"),)


class KeywordTerm(Base):
    __tablename__ = "keyword_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keyword_groups.id"), index=True, nullable=False
    )

    term: Mapped[str] = mapped_column(String(160), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    group: Mapped[KeywordGroup] = relationship(back_populates="terms")

    __table_args__ = (UniqueConstraint("group_id", "term", name="uq_keyword_terms_group_term"),)

