from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument
from app.models.entity_analysis import EntityAnalysis
from app.models.portfolio import PortfolioEntity


def select_light_entity_candidates(db: Session, *, limit: int = 20) -> list[uuid.UUID]:
    now = datetime.now(timezone.utc)
    recent_news_cutoff = now - timedelta(days=1)

    news_ids = db.scalars(
        select(NormalizedNewsDocument.entity_id)
        .where(
            NormalizedNewsDocument.entity_id.isnot(None),
            NormalizedNewsDocument.published_at >= recent_news_cutoff,
        )
        .group_by(NormalizedNewsDocument.entity_id)
        .limit(limit * 2)
    ).all()

    active_metric_ids = db.scalars(
        select(EntityDailyMetric.entity_id)
        .where(EntityDailyMetric.metric_date >= (now.date() - timedelta(days=3)))
        .group_by(EntityDailyMetric.entity_id)
        .limit(limit * 2)
    ).all()

    new_entity_ids = db.scalars(
        select(PortfolioEntity.id)
        .where(PortfolioEntity.created_at >= (now - timedelta(days=1)))
        .limit(limit * 2)
    ).all()

    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for eid in list(new_entity_ids) + list(active_metric_ids) + list(news_ids):
        if eid and eid not in seen:
            seen.add(eid)
            out.append(eid)
        if len(out) >= limit:
            break
    return out


def run_massive_light_analysis_for_entity(db: Session, entity_id: uuid.UUID) -> bool:
    rows = db.scalars(
        select(EntityDailyMetric)
        .where(EntityDailyMetric.entity_id == entity_id)
        .order_by(EntityDailyMetric.metric_date.desc())
        .limit(45)
    ).all()
    if not rows:
        return False
    rows = list(reversed(rows))
    cov = [float(r.coverage_volume or 0.0) for r in rows]
    srch = [float(r.keywords_search_volume or 0.0) for r in rows]
    if not cov and not srch:
        return False

    cov_mean = sum(cov) / max(len(cov), 1)
    srch_mean = sum(srch) / max(len(srch), 1)
    cov_last = cov[-1] if cov else 0.0
    srch_last = srch[-1] if srch else 0.0

    cov_dev = 0.0 if cov_mean == 0 else (cov_last - cov_mean) / abs(cov_mean)
    srch_dev = 0.0 if srch_mean == 0 else (srch_last - srch_mean) / abs(srch_mean)
    event_score = round(max(0.0, min(100.0, ((cov_dev + srch_dev) * 25.0) + 50.0)), 4)
    narrative_strength = round(max(0.0, min(100.0, (abs(cov_dev) + abs(srch_dev)) * 30.0)), 4)
    anomaly_flag = bool(abs(cov_dev - srch_dev) > 0.75)

    stmt = insert(EntityAnalysis).values(
        entity_id=entity_id,
        event_score=event_score,
        anomaly_flag=anomaly_flag,
        narrative_strength=narrative_strength,
        last_analysis_time=datetime.now(timezone.utc),
        analysis_source="narrative_heuristic",
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_entity_analysis_entity",
        set_={
            "event_score": event_score,
            "anomaly_flag": anomaly_flag,
            "narrative_strength": narrative_strength,
            "last_analysis_time": datetime.now(timezone.utc),
            "analysis_source": "narrative_heuristic",
        },
    )
    db.execute(stmt)
    return True
