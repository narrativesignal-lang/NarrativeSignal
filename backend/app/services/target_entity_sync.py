"""Mirror PortfolioEntity into targets.entities for schedule tooling and ad-hoc SQL (same id)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.portfolio import Instrument, PortfolioEntity
from app.models.targets import Entity as TargetEntity


def upsert_target_entity_for_portfolio_entity(db: Session, pe: PortfolioEntity, *, name: str) -> None:
    """Insert or update targets.Entity with the same primary key as portfolio_entities.id."""
    sym = ""
    if pe.instrument_id:
        inst = db.get(Instrument, pe.instrument_id)
        if inst and inst.symbol:
            sym = inst.symbol[:40]
    row = db.get(TargetEntity, pe.id)
    if row is None:
        db.add(
            TargetEntity(
                id=pe.id,
                user_id=pe.user_id,
                name=(name or pe.name or "")[:120],
                symbol=sym,
                entity_type="narrative",
            )
        )
    else:
        row.user_id = pe.user_id
        row.name = (name or pe.name or "")[:120]
        row.symbol = sym


def delete_target_entity_record(db: Session, entity_id: uuid.UUID) -> None:
    row = db.get(TargetEntity, entity_id)
    if row is not None:
        db.delete(row)
