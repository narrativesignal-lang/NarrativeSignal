"""Portfolio → Entity → Terms + Instrument. User-isolated."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    entities: Mapped[list["PortfolioEntity"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan", lazy="selectin"
    )


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    asset_class: Mapped[str] = mapped_column(String(40), nullable=False)
    market: Mapped[str | None] = mapped_column(String(60), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(4), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(60), nullable=True)
    source_priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_instruments_symbol_asset", "symbol", "asset_class"),)


class PortfolioEntity(Base):
    __tablename__ = "portfolio_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), index=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    chart_layout: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    portfolio: Mapped["Portfolio"] = relationship(back_populates="entities")
    instrument: Mapped["Instrument | None"] = relationship(lazy="selectin")
    terms: Mapped[list["EntityTerm"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )
    related_instruments: Mapped[list["EntityRelatedInstrument"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )


class EntityRelatedInstrument(Base):
    """Related instruments for an entity (for comparison / market data cards). Max 8 per entity."""
    __tablename__ = "entity_related_instruments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    entity: Mapped["PortfolioEntity"] = relationship(back_populates="related_instruments")
    instrument: Mapped["Instrument"] = relationship(lazy="selectin")
    __table_args__ = (UniqueConstraint("entity_id", "instrument_id", name="uq_entity_related_instruments_entity_instrument"),)


class EntityTerm(Base):
    __tablename__ = "entity_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_entities.id"), index=True, nullable=False
    )
    term: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    entity: Mapped["PortfolioEntity"] = relationship(back_populates="terms")
    __table_args__ = (UniqueConstraint("entity_id", "normalized_term", name="uq_entity_terms_entity_normalized"),)
