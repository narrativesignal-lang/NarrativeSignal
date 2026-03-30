from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.plan_entitlements import AiAccessLevel, PlanCode
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    credits_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Future billing: use ``PlanCode`` values (``app.core.plan_entitlements``). Not yet used for AI gating.
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, default=PlanCode.FREE.value)
    #: Future billing: use ``AiAccessLevel`` values. Not yet used; see ``feature_access``.
    ai_access_level: Mapped[str] = mapped_column(String(32), nullable=False, default=AiAccessLevel.NONE.value)
    #: Subscription / paid tier flag — timeline unlock requires paid_access and credits_balance > 0 (admins bypass).
    paid_access: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_admin: Mapped[bool] = mapped_column(nullable=False, default=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: User-facing display name (not login identifier).
    profile_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

