"""Entity daily metrics: Google Trends + DB as source of truth (no null-out on failed sync)."""

from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument
from app.models.portfolio import PortfolioEntity
from app.services.cache_fallback import utcnow
from app.services.entity_chart_3d import (
    _CHART3D_RANGE_DAYS,
    _iter_chart3d_dates,
    coverage_volume_mock_for_day,
    normalize_chart_3d_range,
)
from app.services.trends_service import get_daily_search_trend, normalize_trends_timeframe

logger = logging.getLogger(__name__)


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _generate_mock_search_trend_series(entity_id: uuid.UUID, days: int = 90) -> list[dict[str, float | str]]:
    """
    Deterministic local fallback when Google Trends is unavailable.
    Values stay in [20, 80] with gentle trend + low noise, seeded by entity_id.
    """
    end_day = date.today()
    start_day = end_day - timedelta(days=days - 1)
    seed = int(entity_id.hex[:16], 16)
    rng = random.Random(seed)
    base = 35.0 + (seed % 15)  # 35..49
    slope = ((seed % 9) - 4) / 120.0  # slight up/down drift
    out: list[dict[str, float | str]] = []
    for i in range(days):
        d = start_day + timedelta(days=i)
        noise = rng.uniform(-2.5, 2.5)
        v = base + (i * slope) + noise
        v = max(20.0, min(80.0, round(v, 4)))
        out.append({"date": d.isoformat(), "search_trend": v})
    return out


def coverage_from_deduped_docs(db: Session, entity_id: uuid.UUID, day: date) -> int | None:
    """
    Count distinct story clusters for entity on calendar day (UTC).
    Returns None if this entity has never had any normalized doc row (use pipeline mock instead).
    """
    total_any = db.scalar(
        select(func.count()).select_from(NormalizedNewsDocument).where(NormalizedNewsDocument.entity_id == entity_id)
    )
    if not total_any:
        return None
    start = _day_start(day)
    end = start + timedelta(days=1)
    n = db.scalar(
        select(func.count(func.distinct(NormalizedNewsDocument.dedup_cluster_id))).where(
            NormalizedNewsDocument.entity_id == entity_id,
            NormalizedNewsDocument.published_at >= start,
            NormalizedNewsDocument.published_at < end,
            NormalizedNewsDocument.dedup_cluster_id.isnot(None),
        )
    )
    return int(n or 0)


def sync_entity_search_trend(
    db: Session,
    entity_id: uuid.UUID,
    *,
    timeframe: str | None = None,
) -> int:
    """
    Pull daily search interest from Google Trends (pytrends) and upsert entity_daily_metrics.search_trend only.
    On full fetch failure: returns 0 and does not modify existing rows.
    Never clears coverage_volume.
    """
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == entity_id).options(selectinload(PortfolioEntity.terms))
    )
    if not entity:
        return 0
    terms = [t.term for t in entity.terms]
    if not terms:
        return 0

    tf = normalize_trends_timeframe(timeframe)
    series = get_daily_search_trend(terms, tf)
    source = "google_trends"
    if not series:
        series = _generate_mock_search_trend_series(entity_id, days=90)
        source = "mock_fallback"
        logger.info("entity metrics fallback engaged entity_id=%s rows=%d", entity_id, len(series))

    now = utcnow()
    n = 0
    for p in series:
        try:
            d = date.fromisoformat(str(p["date"]))
            new_st = float(p["search_trend"])
        except Exception:
            continue
        row = db.scalar(
            select(EntityDailyMetric).where(
                EntityDailyMetric.entity_id == entity_id,
                EntityDailyMetric.metric_date == d,
            )
        )
        if row is None:
            db.add(
                EntityDailyMetric(
                    entity_id=entity_id,
                    metric_date=d,
                    search_trend=new_st,
                    search_trend_source=source,
                    coverage_volume=None,
                    sentiment_score=None,
                    coverage_volume_source=None,
                    last_success_at=now,
                    last_error=None,
                    is_stale=False,
                )
            )
        else:
            row.search_trend = new_st
            row.search_trend_source = source
            row.last_success_at = now
            row.last_error = None
            row.is_stale = False
        n += 1

    # Hard guarantee: any entity with valid terms must write fallback rows locally.
    if n == 0:
        series_fb = _generate_mock_search_trend_series(entity_id, days=90)
        for p in series_fb:
            d = date.fromisoformat(str(p["date"]))
            new_st = float(p["search_trend"])
            row = db.scalar(
                select(EntityDailyMetric).where(
                    EntityDailyMetric.entity_id == entity_id,
                    EntityDailyMetric.metric_date == d,
                )
            )
            if row is None:
                db.add(
                    EntityDailyMetric(
                        entity_id=entity_id,
                        metric_date=d,
                        search_trend=new_st,
                        search_trend_source="mock_fallback",
                        coverage_volume=None,
                        sentiment_score=None,
                        coverage_volume_source=None,
                        last_success_at=now,
                        last_error=None,
                        is_stale=False,
                    )
                )
            else:
                row.search_trend = new_st
                row.search_trend_source = "mock_fallback"
                row.last_success_at = now
                row.last_error = None
                row.is_stale = False
            n += 1
        logger.info("entity metrics fallback rows written entity_id=%s rows=%d", entity_id, n)
    return n


def get_chart_3d_payload(
    db: Session,
    entity_id: uuid.UUID,
    terms: list[str],
    range_key: str,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    """
    Read search_trend from entity_daily_metrics (forward-filled). No random search_trend.
    coverage_volume: DB → dedup → deterministic mock fallback only.
    """
    rk = normalize_chart_3d_range(range_key)
    days = _CHART3D_RANGE_DAYS[rk]
    start_day = date.today() - timedelta(days=days + 2)
    rows = db.scalars(
        select(EntityDailyMetric)
        .where(EntityDailyMetric.entity_id == entity_id, EntityDailyMetric.metric_date >= start_day)
        .order_by(EntityDailyMetric.metric_date)
    ).all()
    by_db = {r.metric_date.isoformat(): r for r in rows}

    date_list = _iter_chart3d_dates(rk)
    carry_st: float | None = None
    out: list[dict[str, float | str]] = []
    st_src = "mock"
    has_real_cov = False

    for d in date_list:
        br = by_db.get(d)
        if br is not None and br.search_trend is not None:
            carry_st = float(br.search_trend)
            if (br.search_trend_source or "") in {"google_trends", "real", "mock_fallback"}:
                st_src = "real"

        if carry_st is None:
            continue

        st = float(br.search_trend) if br is not None and br.search_trend is not None else carry_st

        day_date = date.fromisoformat(d)
        if br is not None and br.coverage_volume is not None:
            cv = float(br.coverage_volume)
            if (br.coverage_volume_source or "") == "real":
                has_real_cov = True
        else:
            cov_db = coverage_from_deduped_docs(db, entity_id, day_date)
            if cov_db is not None:
                cv = float(cov_db)
                has_real_cov = True
            else:
                cv = coverage_volume_mock_for_day(terms, str(entity_id), d)

        out.append({"date": d, "search_trend": st, "coverage_volume": cv})

    cv_src = "real" if has_real_cov else "mock"

    return out, {"search_trend": st_src or "mock", "coverage_volume": cv_src or "mock"}


def get_entity_search_trend_timeseries(
    db: Session,
    entity_id: uuid.UUID,
    terms: list[str],
    range_key: str,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    """Read-only from entity_daily_metrics (no mock)."""
    _ = terms  # reserved for future filters
    rk = normalize_chart_3d_range(range_key)
    days = _CHART3D_RANGE_DAYS[rk]
    start_day = date.today() - timedelta(days=days + 2)
    rows = db.scalars(
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= start_day,
            EntityDailyMetric.search_trend.isnot(None),
        )
        .order_by(EntityDailyMetric.metric_date)
    ).all()
    series = [{"date": r.metric_date.isoformat(), "search_trend": float(r.search_trend)} for r in rows]
    st_src = "real" if any((r.search_trend_source or "") == "google_trends" for r in rows) else "mock"
    return series, {"search_trend": st_src}
