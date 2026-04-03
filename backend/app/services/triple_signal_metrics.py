from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.data_subscription import EntityDailyMetric, EntityTripleSignalDaily, OhlcvSnapshot
from app.models.portfolio import PortfolioEntity

ROLLING_WINDOW_DAYS = 30


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int((len(sorted_vals) - 1) * q)
    idx = max(0, min(len(sorted_vals) - 1, idx))
    return float(sorted_vals[idx])


def _normalize_window(series: list[float], value: float) -> float:
    if not series:
        return 0.0
    s = sorted(float(x) for x in series)
    lo = _percentile(s, 0.05)
    hi = _percentile(s, 0.95)
    if hi <= lo:
        return 50.0
    v = max(lo, min(hi, float(value)))
    return round(((v - lo) / (hi - lo)) * 100.0, 4)


def _parse_ohlcv_daily_volume(snapshot_bars: dict[str, Any] | None) -> dict[date, float]:
    out: dict[date, float] = {}
    bars = (snapshot_bars or {}).get("bars", []) if isinstance(snapshot_bars, dict) else []
    for b in bars:
        if not isinstance(b, dict):
            continue
        ts = b.get("time")
        vol = b.get("volume")
        if ts is None or vol is None:
            continue
        try:
            d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            out[d] = float(vol)
        except Exception:
            continue
    return out


def upsert_entity_triple_signal_metrics(db: Session, entity_id: uuid.UUID, *, days: int = ROLLING_WINDOW_DAYS) -> int:
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == entity_id)
    )
    if not entity:
        return 0

    start_day = date.today() - timedelta(days=days + 90)
    metric_rows = db.scalars(
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= start_day,
        )
        .order_by(EntityDailyMetric.metric_date.asc())
    ).all()

    search_raw_by_day: dict[date, float] = {}
    news_raw_by_day: dict[date, float] = {}
    for r in metric_rows:
        if r.keywords_search_volume is not None and (r.keywords_search_volume_source or "").lower() in {
            "google_trends",
            "real",
        }:
            search_raw_by_day[r.metric_date] = float(r.keywords_search_volume)
        if r.coverage_volume is not None:
            news_raw_by_day[r.metric_date] = float(r.coverage_volume)

    symbol = (entity.instrument.symbol if entity.instrument else "").strip().upper()
    ohlcv_raw_by_day: dict[date, float] = {}
    if symbol:
        snap = db.get(OhlcvSnapshot, f"{symbol}:1Y")
        if snap and snap.bars:
            ohlcv_raw_by_day = _parse_ohlcv_daily_volume(snap.bars)

    all_days = sorted(set(search_raw_by_day.keys()) | set(news_raw_by_day.keys()) | set(ohlcv_raw_by_day.keys()))
    if not all_days:
        return 0

    latest_start = date.today() - timedelta(days=days - 1)
    affected = 0
    for d in all_days:
        if d < latest_start:
            continue
        window_start = d - timedelta(days=days - 1)
        trade_window = [v for dd, v in ohlcv_raw_by_day.items() if window_start <= dd <= d]
        news_window = [v for dd, v in news_raw_by_day.items() if window_start <= dd <= d]
        search_window = [v for dd, v in search_raw_by_day.items() if window_start <= dd <= d]
        trade_now = ohlcv_raw_by_day.get(d)
        news_now = news_raw_by_day.get(d)
        search_now = search_raw_by_day.get(d)
        if trade_now is None and news_now is None and search_now is None:
            continue
        trading_activity = _normalize_window(trade_window, trade_now or 0.0) if trade_now is not None else 0.0
        news_volume = _normalize_window(news_window, news_now or 0.0) if news_now is not None else 0.0
        search_volume = _normalize_window(search_window, search_now or 0.0) if search_now is not None else 0.0
        stmt = insert(EntityTripleSignalDaily).values(
            entity_id=entity_id,
            metric_date=d,
            trading_activity=trading_activity,
            news_volume=news_volume,
            search_volume=search_volume,
            last_updated=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_entity_triple_signal_day",
            set_={
                "trading_activity": trading_activity,
                "news_volume": news_volume,
                "search_volume": search_volume,
                "last_updated": datetime.now(timezone.utc),
            },
        )
        db.execute(stmt)
        affected += 1
    db.commit()
    return affected


def read_entity_triple_signal_series(db: Session, entity_id: uuid.UUID, *, period_days: int = 90) -> list[dict[str, float | str]]:
    start_day = date.today() - timedelta(days=period_days + 2)
    rows = db.scalars(
        select(EntityTripleSignalDaily)
        .where(
            EntityTripleSignalDaily.entity_id == entity_id,
            EntityTripleSignalDaily.metric_date >= start_day,
        )
        .order_by(EntityTripleSignalDaily.metric_date.asc())
    ).all()
    return [
        {
            "date": r.metric_date.isoformat(),
            "trading_activity": float(r.trading_activity),
            "news_volume": float(r.news_volume),
            "search_volume": float(r.search_volume),
        }
        for r in rows
    ]


def read_entity_triple_signal_series_aligned(
    db: Session,
    entity_id: uuid.UUID,
    *,
    period_days: int = 90,
) -> dict[str, Any]:
    """
    Return a unified daily date axis + per-series values (null gaps allowed).
    Values are taken from entity_triple_signal_daily but set to None when the underlying
    raw source is missing on that date (e.g. no real pytrends row → search_volume=None).
    """
    start_day = date.today() - timedelta(days=period_days - 1)
    end_day = date.today()
    axis: list[date] = []
    d = start_day
    while d <= end_day:
        axis.append(d)
        d = d + timedelta(days=1)

    ts_rows = db.scalars(
        select(EntityTripleSignalDaily)
        .where(
            EntityTripleSignalDaily.entity_id == entity_id,
            EntityTripleSignalDaily.metric_date >= start_day,
            EntityTripleSignalDaily.metric_date <= end_day,
        )
        .order_by(EntityTripleSignalDaily.metric_date.asc())
    ).all()
    by_day = {r.metric_date: r for r in ts_rows}

    # Availability maps (raw sources)
    metric_rows = db.scalars(
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= start_day,
            EntityDailyMetric.metric_date <= end_day,
        )
        .order_by(EntityDailyMetric.metric_date.asc())
    ).all()
    has_real_search: set[date] = set()
    has_news: set[date] = set()
    for r in metric_rows:
        if r.keywords_search_volume is not None and (r.keywords_search_volume_source or "").lower() in {
            "google_trends",
            "real",
        }:
            has_real_search.add(r.metric_date)
        if r.coverage_volume is not None:
            has_news.add(r.metric_date)

    entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == entity_id))
    symbol = (entity.instrument.symbol if entity and entity.instrument else "").strip().upper()
    has_trade: set[date] = set()
    if symbol:
        snap = db.get(OhlcvSnapshot, f"{symbol}:1Y")
        if snap and isinstance(snap.bars, dict):
            bars = (snap.bars or {}).get("bars") or []
            if isinstance(bars, list):
                for b in bars:
                    if not isinstance(b, dict):
                        continue
                    ts = b.get("time")
                    if ts is None:
                        continue
                    try:
                        has_trade.add(datetime.fromtimestamp(int(ts), tz=timezone.utc).date())
                    except Exception:
                        continue

    axis_s = [dd.isoformat() for dd in axis]
    trading: list[float | None] = []
    news: list[float | None] = []
    search: list[float | None] = []
    last_updated: datetime | None = None

    for dd in axis:
        row = by_day.get(dd)
        if row and (last_updated is None or row.last_updated > last_updated):
            last_updated = row.last_updated
        trading.append(float(row.trading_activity) if (row is not None and dd in has_trade) else None)
        news.append(float(row.news_volume) if (row is not None and dd in has_news) else None)
        search.append(float(row.search_volume) if (row is not None and dd in has_real_search) else None)

    return {
        "axis": axis_s,
        "trading_activity": trading,
        "news_volume": news,
        "search_volume": search,
        "last_updated_at": last_updated.isoformat() if last_updated else None,
    }
