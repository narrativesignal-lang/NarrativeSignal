"""Unified entity metric timeseries service (base + derived metrics)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_subscription import EntityDailyMetric
from app.services.entity_chart_3d import _CHART3D_RANGE_DAYS, normalize_chart_3d_range

_ALLOWED_BASE = {"target_search_volume", "keywords_search_volume", "coverage_volume", "sentiment_score"}
_ALLOWED_DERIVED = {
    "momentum_target",
    "acceleration_target",
    "momentum_keywords",
    "acceleration_keywords",
}


def _day_window(range_key: str) -> date:
    rk = normalize_chart_3d_range(range_key)
    return date.today() - timedelta(days=_CHART3D_RANGE_DAYS[rk] + 2)


def _first_derivative(points: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    out: list[dict[str, float | str]] = []
    prev: float | None = None
    for p in points:
        v = float(p["value"])
        d = 0.0 if prev is None else round(v - prev, 6)
        out.append({"date": p["date"], "value": d})
        prev = v
    return out


def get_entity_metric_timeseries(
    db: Session,
    entity_id: uuid.UUID,
    metric_name: str,
    *,
    range_key: str = "3m",
) -> list[dict[str, float | str]]:
    """
    Unified metric reader. All charts should consume this service.
    - base: target_search_volume / keywords_search_volume / coverage_volume / sentiment_score
    - derived: momentum_* / acceleration_* (per tool, from respective base)
    """
    m = (metric_name or "").strip().lower()
    if m in _ALLOWED_DERIVED:
        base_metric = (
            "target_search_volume"
            if m in ("momentum_target", "acceleration_target")
            else "keywords_search_volume"
        )
        base = get_entity_metric_timeseries(db, entity_id, base_metric, range_key=range_key)
        d1 = _first_derivative(base)
        if m in ("momentum_target", "momentum_keywords"):
            return d1
        return _first_derivative(d1)

    if m not in _ALLOWED_BASE:
        raise ValueError(f"unsupported metric: {metric_name}")

    start_day = _day_window(range_key)
    stmt = (
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= start_day,
        )
        .order_by(EntityDailyMetric.metric_date.asc())
    )
    if m == "target_search_volume":
        stmt = stmt.where(EntityDailyMetric.target_search_volume_source.in_(["google_trends", "real"]))
    elif m == "keywords_search_volume":
        stmt = stmt.where(EntityDailyMetric.keywords_search_volume_source.in_(["google_trends", "real"]))
    rows = db.scalars(stmt).all()

    out: list[dict[str, float | str]] = []
    carry: float | None = None
    for r in rows:
        raw = getattr(r, m)
        if raw is None:
            if carry is None:
                continue
            v = carry
        else:
            v = float(raw)
            carry = v
        out.append({"date": r.metric_date.isoformat(), "value": float(v)})
    return out

