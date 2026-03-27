"""
Shared narrative metric reads for portfolio entities (tracking) and keyword groups (group indices).

Routes stay thin; Entity vs Research UIs can call different endpoints while reusing this layer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_subscription import EntityDailyMetric
from app.models.index_point import IndexPoint
from app.models.keyword_group import KeywordGroup
from app.services.entity_metrics_service import get_entity_metric_timeseries


def range_key_from_series_period(period: str) -> str:
    """Align chart period with entity_daily_metrics windows (search/coverage/sentiment series)."""
    p = period.strip().upper() if period else "1M"
    return "3m" if p in {"3M", "6M", "1Y", "MAX"} else "1m"


def range_key_from_quadrant_history_period(period: str) -> str:
    period_upper = (period.strip().upper() or "1M")
    return "1m" if period_upper in {"7D", "1M"} else "3m"


def entity_daily_metric_last_success(db: Session, entity_id: uuid.UUID) -> datetime | None:
    return db.scalar(
        select(EntityDailyMetric.last_success_at)
        .where(EntityDailyMetric.entity_id == entity_id)
        .order_by(EntityDailyMetric.metric_date.desc())
        .limit(1)
    )


def entity_metric_timeseries_bundle(
    db: Session, entity_id: uuid.UUID, metric_name: str, period: str
) -> tuple[list[dict], datetime | None, bool]:
    """
    Returns (points as {"t": iso_date, "value": float}, last_success_at, stale).
    When there are no rows, emits one zero point for stable UI shape (same as portfolios routes).
    """
    rk = range_key_from_series_period(period)
    rows = get_entity_metric_timeseries(db, entity_id, metric_name, range_key=rk)
    last = entity_daily_metric_last_success(db, entity_id)
    stale = len(rows) == 0
    points: list[dict] = [{"t": str(r["date"]), "value": float(r["value"])} for r in rows]
    if not points:
        points = [{"t": date.today().isoformat(), "value": 0.0}]
    return points, last, stale


def entity_quadrant_current_bundle(
    db: Session, entity_id: uuid.UUID
) -> tuple[float, float, datetime | None, bool]:
    s = get_entity_metric_timeseries(db, entity_id, "momentum", range_key="3m")
    c = get_entity_metric_timeseries(db, entity_id, "coverage_volume", range_key="3m")
    sv = float(s[-1]["value"]) if s else 0.0
    cv = float(c[-1]["value"]) if c else 0.0
    last = entity_daily_metric_last_success(db, entity_id)
    return sv, cv, last, not bool(last)


def entity_quadrant_history_bundle(
    db: Session, entity_id: uuid.UUID, period: str
) -> tuple[list[dict], datetime | None, bool]:
    rk = range_key_from_quadrant_history_period(period)
    s = get_entity_metric_timeseries(db, entity_id, "momentum", range_key=rk)
    c = get_entity_metric_timeseries(db, entity_id, "coverage_volume", range_key=rk)
    by_date = {str(x["date"]): float(x["value"]) for x in s}
    points: list[dict] = [
        {
            "t": str(x["date"]),
            "coverage_momentum": float(x["value"]),
            "search_momentum": float(by_date.get(str(x["date"]), 0.0)),
        }
        for x in c
    ]
    last = entity_daily_metric_last_success(db, entity_id)
    if not points:
        points = [{"t": date.today().isoformat(), "coverage_momentum": 0.0, "search_momentum": 0.0}]
    return points, last, not bool(last)


def trend_label_from_momenta(search_momentum: float, coverage_momentum: float, sentiment_change: float) -> str:
    if search_momentum > 0 and coverage_momentum > 0:
        return "Rising"
    if search_momentum < 0 and coverage_momentum < 0:
        return "Fading"
    if sentiment_change > 25 or (search_momentum > 30 and coverage_momentum > 30):
        return "Spike"
    return "Neutral"


def entity_trending_bundle(
    db: Session, entity_id: uuid.UUID
) -> tuple[float, float, float, str, datetime | None, bool]:
    s = get_entity_metric_timeseries(db, entity_id, "momentum", range_key="3m")
    c = get_entity_metric_timeseries(db, entity_id, "coverage_volume", range_key="3m")
    ss = get_entity_metric_timeseries(db, entity_id, "sentiment_score", range_key="3m")
    search_m = float(s[-1]["value"]) if s else 0.0
    coverage_m = float(c[-1]["value"]) if c else 0.0
    sentiment_change = 0.0
    if len(ss) >= 2:
        sentiment_change = float(ss[-1]["value"]) - float(ss[-2]["value"])
    label = trend_label_from_momenta(search_m, coverage_m, sentiment_change)
    last = entity_daily_metric_last_success(db, entity_id)
    return search_m, coverage_m, sentiment_change, label, last, not bool(last)


def fetch_keyword_group_index_points(
    db: Session, user_id: uuid.UUID, group_id: uuid.UUID, hours: int
) -> list[IndexPoint]:
    group = db.scalar(select(KeywordGroup).where(KeywordGroup.id == group_id, KeywordGroup.user_id == user_id))
    if not group:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return list(
        db.scalars(
            select(IndexPoint)
            .where(IndexPoint.group_id == group_id, IndexPoint.bucket_start >= since)
            .order_by(IndexPoint.bucket_start.asc())
        ).all()
    )
