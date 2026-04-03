from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.massive_backfill_queue import MassiveBackfillQueueEntry


def enqueue_massive_backfill(
    db: Session,
    *,
    symbol: str,
    entity_id: uuid.UUID | None,
    asset_class: str | None,
    need_quote: bool,
    need_ohlcv: bool,
    priority: int = 0,
    source_reason: str | None = None,
    not_before: datetime | None = None,
) -> bool:
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    if not need_quote and not need_ohlcv:
        return False
    nb = not_before
    if nb is None:
        nb = datetime.now(timezone.utc)
    if nb.tzinfo is None:
        nb = nb.replace(tzinfo=timezone.utc)

    stmt = insert(MassiveBackfillQueueEntry).values(
        symbol=sym,
        entity_id=entity_id,
        asset_class=(asset_class or None),
        need_quote=bool(need_quote),
        need_ohlcv=bool(need_ohlcv),
        priority=int(priority or 0),
        source_reason=(source_reason or None),
        status="pending",
        retry_count=0,
        last_attempt_at=None,
        next_attempt_at=nb,
        provider_last_used=None,
        last_error=None,
        updated_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_massive_backfill_symbol_need",
        set_={
            # Keep highest priority (don't downgrade).
            "priority": MassiveBackfillQueueEntry.priority
            if int(priority or 0) <= 0
            else (priority if priority > 0 else MassiveBackfillQueueEntry.priority),
            # Merge entity_id if newly available.
            "entity_id": MassiveBackfillQueueEntry.entity_id
            if entity_id is None
            else entity_id,
            "asset_class": MassiveBackfillQueueEntry.asset_class if not asset_class else asset_class,
            # If item was done/failed/paused, allow requeue by setting pending + next_attempt.
            "status": "pending",
            "next_attempt_at": nb,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    db.execute(stmt)
    return True


def pick_pending_backfill_rows(db: Session, *, limit: int) -> list[MassiveBackfillQueueEntry]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(MassiveBackfillQueueEntry)
        .where(
            MassiveBackfillQueueEntry.status == "pending",
            (MassiveBackfillQueueEntry.next_attempt_at.is_(None))
            | (MassiveBackfillQueueEntry.next_attempt_at <= now),
        )
        .order_by(MassiveBackfillQueueEntry.priority.desc(), MassiveBackfillQueueEntry.created_at.asc())
        .limit(int(limit))
    )
    return list(db.scalars(stmt).all())


def backoff_next_attempt(retry_count: int) -> datetime:
    now = datetime.now(timezone.utc)
    n = int(retry_count or 0)
    # quick backoff for queue items (separate from provider pause)
    minutes = 10 if n <= 1 else 30 if n == 2 else 60 if n == 3 else 180
    return now + timedelta(minutes=minutes)

