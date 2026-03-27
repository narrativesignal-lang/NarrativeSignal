"""Register and query user_data_subscriptions."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_subscription import UserDataSubscription

logger = logging.getLogger(__name__)


def ensure_subscription(
    db: Session,
    *,
    user_id: uuid.UUID,
    source_type: str,
    target_type: str,
    target_id: str,
    frequency: str = "daily",
    extra: dict | None = None,
) -> UserDataSubscription:
    tid = str(target_id).strip()
    existing = db.scalar(
        select(UserDataSubscription).where(
            UserDataSubscription.user_id == user_id,
            UserDataSubscription.source_type == source_type,
            UserDataSubscription.target_type == target_type,
            UserDataSubscription.target_id == tid,
        )
    )
    if existing:
        if extra and existing.extra != extra:
            existing.extra = {**(existing.extra or {}), **extra}
        if not existing.is_active:
            existing.is_active = True
        logger.info(
            "subscription ensured existing user_id=%s source=%s target_type=%s target_id=%s",
            user_id,
            source_type,
            target_type,
            tid,
        )
        return existing
    sub = UserDataSubscription(
        user_id=user_id,
        source_type=source_type,
        target_type=target_type,
        target_id=tid,
        frequency=frequency,
        is_active=True,
        extra=extra,
    )
    db.add(sub)
    logger.info(
        "subscription created user_id=%s source=%s target_type=%s target_id=%s",
        user_id,
        source_type,
        target_type,
        tid,
    )
    return sub


def register_entity_subscriptions(db: Session, user_id: uuid.UUID, entity_id: uuid.UUID) -> None:
    eid = str(entity_id)
    ensure_subscription(db, user_id=user_id, source_type="search_trend", target_type="entity", target_id=eid, frequency="daily")
    ensure_subscription(db, user_id=user_id, source_type="news_coverage", target_type="entity", target_id=eid, frequency="daily")
    ensure_subscription(db, user_id=user_id, source_type="entity_news", target_type="entity", target_id=eid, frequency="daily")


def register_instrument_quote_subscription(db: Session, user_id: uuid.UUID, symbol: str) -> None:
    """Watchlist / index row: refresh market quote on a schedule."""
    sym = symbol.strip().upper()
    ensure_subscription(
        db,
        user_id=user_id,
        source_type="market_quote",
        target_type="instrument",
        target_id=sym,
        frequency="15m",
        extra={"symbol": sym},
    )


def register_keyword_group_subscriptions(db: Session, user_id: uuid.UUID, group_id: uuid.UUID) -> None:
    gid = str(group_id)
    ensure_subscription(db, user_id=user_id, source_type="news_feed", target_type="keyword_group", target_id=gid, frequency="daily")
    ensure_subscription(db, user_id=user_id, source_type="news_coverage", target_type="keyword_group", target_id=gid, frequency="daily")


def register_research_project_subscriptions(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Research workspace: news feeds + coverage for project-level summaries."""
    pid = str(project_id)
    ensure_subscription(db, user_id=user_id, source_type="news_feed", target_type="research_project", target_id=pid, frequency="daily")
    ensure_subscription(db, user_id=user_id, source_type="news_coverage", target_type="research_project", target_id=pid, frequency="daily")


def remove_entity_subscriptions(db: Session, user_id: uuid.UUID, entity_id: uuid.UUID) -> int:
    """Hard-remove all entity-scoped subscriptions for a deleted entity."""
    eid = str(entity_id)
    rows = db.scalars(
        select(UserDataSubscription).where(
            UserDataSubscription.user_id == user_id,
            UserDataSubscription.target_type == "entity",
            UserDataSubscription.target_id == eid,
        )
    ).all()
    for r in rows:
        db.delete(r)
    if rows:
        logger.info("entity subscriptions removed user_id=%s entity_id=%s count=%d", user_id, entity_id, len(rows))
    return len(rows)
