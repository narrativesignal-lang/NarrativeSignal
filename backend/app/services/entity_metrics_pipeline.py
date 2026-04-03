"""Entity daily metrics: real sources only (no synthetic fallback writes)."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument
from app.models.portfolio import PortfolioEntity
from app.services.cache_fallback import utcnow
from app.services.entity_chart_3d import _CHART3D_RANGE_DAYS, _iter_chart3d_dates, normalize_chart_3d_range
from app.services.runtime_flags import pytrends_enabled
from app.services.trends_service import get_daily_interest_single_keyword, normalize_trends_timeframe

logger = logging.getLogger(__name__)

_GOOGLE = ("google_trends", "real")


def _norm_sym(s: str | None) -> str:
    return (s or "").strip().upper()


def entity_target_and_narrative_keywords(entity: PortfolioEntity) -> tuple[str | None, list[str]]:
    """
    Target = primary instrument symbol (investor intent). Narrative = entity terms excluding that symbol.
    """
    target: str | None = None
    if entity.instrument and entity.instrument.symbol:
        t = entity.instrument.symbol.strip()
        target = t or None
    target_key = _norm_sym(target)
    narrative: list[str] = []
    seen: set[str] = set()
    for term_row in entity.terms or []:
        raw = (term_row.term or "").strip()
        if not raw:
            continue
        if target_key and _norm_sym(raw) == target_key:
            continue
        lk = raw.lower()
        if lk in seen:
            continue
        seen.add(lk)
        narrative.append(raw)
    return target, narrative


def last_keywords_search_success_at(db: Session, entity_id: uuid.UUID) -> datetime | None:
    return db.scalar(
        select(EntityDailyMetric.last_success_at)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.keywords_search_volume.isnot(None),
            EntityDailyMetric.keywords_search_volume_source.in_(list(_GOOGLE)),
        )
        .order_by(EntityDailyMetric.metric_date.desc())
        .limit(1)
    )


def last_target_search_success_at(db: Session, entity_id: uuid.UUID) -> datetime | None:
    return db.scalar(
        select(EntityDailyMetric.last_success_at)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.target_search_volume.isnot(None),
            EntityDailyMetric.target_search_volume_source.in_(list(_GOOGLE)),
        )
        .order_by(EntityDailyMetric.metric_date.desc())
        .limit(1)
    )


def last_search_trend_success_at(db: Session, entity_id: uuid.UUID) -> datetime | None:
    """Backward compat: latest success on narrative (keywords) leg."""
    return last_keywords_search_success_at(db, entity_id)


def explain_search_volumes_absence(
    db: Session, entity_id: uuid.UUID, *, has_target: bool, has_narrative_terms: bool
) -> str:
    if not pytrends_enabled(db):
        return "Search volume updates are disabled."
    if not has_target and not has_narrative_terms:
        return "Link an instrument (for target search) and/or add narrative keywords for Trends data."
    row = db.scalar(
        select(EntityDailyMetric)
        .where(EntityDailyMetric.entity_id == entity_id)
        .order_by(EntityDailyMetric.metric_date.desc())
        .limit(1)
    )
    if row is not None:
        err = (row.last_error or "").strip().lower()
        if "pytrends" in err:
            return "Google Trends could not load data (network, rate limit, or regional block). Try again later."
    return "No search volume data in this range yet. Save terms or wait for the next sync."


def explain_search_trend_absence(db: Session, entity_id: uuid.UUID, terms: list[str]) -> str:
    _ = terms
    entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == entity_id).options(selectinload(PortfolioEntity.instrument)))
    tgt, narr = (None, [])
    if entity:
        tgt, narr = entity_target_and_narrative_keywords(entity)
    return explain_search_volumes_absence(db, entity_id, has_target=bool(tgt), has_narrative_terms=bool(narr))


def explain_chart_3d_absence(
    db: Session,
    entity_id: uuid.UUID,
    terms: list[str],
    src_status: dict[str, str],
) -> str:
    """When the 3D path has zero points, describe the blocking leg (keywords search vs coverage vs alignment)."""
    kws = (src_status.get("keywords_search_volume") or "").strip().lower()
    cv = (src_status.get("coverage_volume") or "").strip().lower()
    if not [x.strip() for x in terms if x and str(x).strip()]:
        return "Add narrative keywords to use the narrative search axis (or rely on instrument for target-only views)."
    if kws != "real":
        entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == entity_id).options(selectinload(PortfolioEntity.instrument)))
        tgt, narr = (None, [])
        if entity:
            tgt, narr = entity_target_and_narrative_keywords(entity)
        return explain_search_volumes_absence(db, entity_id, has_target=bool(tgt), has_narrative_terms=bool(narr))
    if cv != "real":
        return "Keywords search data exists; news coverage is still building for overlapping days. Try a wider range or wait for news ingestion."
    return "No day in this range has both keywords search volume and news coverage."


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


_LOW_QUALITY_SOURCE_WORDS = {
    "substack",
    "medium",
    "blog",
    "wordpress",
    "blogspot",
    "tumblr",
    "reddit",
    "tiktok",
    "youtube",
    "facebook",
    "telegram",
    "discord",
    "x.com",
    "twitter",
}
_LOW_QUALITY_HOSTS = {
    "medium.com",
    "substack.com",
    "wordpress.com",
    "blogspot.com",
    "tumblr.com",
    "reddit.com",
    "old.reddit.com",
    "m.youtube.com",
    "youtube.com",
    "youtu.be",
    "t.co",
    "x.com",
    "twitter.com",
    "m.facebook.com",
    "facebook.com",
    "t.me",
}


def _is_low_quality_source(*, canonical_url: str | None, raw_sources: dict | None) -> bool:
    try:
        src = ""
        if raw_sources and isinstance(raw_sources, dict):
            src = str(raw_sources.get("source") or "").strip().lower()
        if src and any(w in src for w in _LOW_QUALITY_SOURCE_WORDS):
            return True
    except Exception:
        pass
    try:
        if canonical_url:
            from urllib.parse import urlparse

            host = (urlparse(canonical_url).hostname or "").lower()
            if host in _LOW_QUALITY_HOSTS:
                return True
    except Exception:
        pass
    return False


def coverage_from_deduped_docs(db: Session, entity_id: uuid.UUID, day: date) -> int | None:
    total_any = db.scalar(
        select(func.count()).select_from(NormalizedNewsDocument).where(NormalizedNewsDocument.entity_id == entity_id)
    )
    if not total_any:
        return None
    start = _day_start(day)
    end = start + timedelta(days=1)
    docs = db.scalars(
        select(NormalizedNewsDocument).where(
            NormalizedNewsDocument.entity_id == entity_id,
            NormalizedNewsDocument.published_at >= start,
            NormalizedNewsDocument.published_at < end,
        )
    ).all()
    if not docs:
        return 0
    kept = [d for d in docs if not _is_low_quality_source(canonical_url=d.canonical_url, raw_sources=d.raw_sources)]
    return int(len(kept))


def _is_postgres(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def _upsert_search_volumes_success(
    db: Session,
    entity_id: uuid.UUID,
    metric_date: date,
    now: datetime,
    *,
    target_volume: float | None,
    set_target: bool,
    keywords_volume: float | None,
    set_keywords: bool,
) -> None:
    """Merge target + keywords columns; omitted legs leave existing values (COALESCE)."""
    if _is_postgres(db):
        tbl = EntityDailyMetric.__table__
        ins = pg_insert(EntityDailyMetric).values(
            id=uuid.uuid4(),
            entity_id=entity_id,
            metric_date=metric_date,
            target_search_volume=target_volume if set_target else None,
            target_search_volume_source=("google_trends" if set_target else None),
            keywords_search_volume=keywords_volume if set_keywords else None,
            keywords_search_volume_source=("google_trends" if set_keywords else None),
            search_trend=None,
            search_trend_source=None,
            coverage_volume=None,
            sentiment_score=None,
            coverage_volume_source=None,
            last_success_at=now,
            last_error=None,
            is_stale=False,
            extra=None,
        )
        stmt = ins.on_conflict_do_update(
            constraint="uq_entity_daily_metric_day",
            set_={
                "target_search_volume": func.coalesce(ins.excluded.target_search_volume, tbl.c.target_search_volume),
                "target_search_volume_source": case(
                    (ins.excluded.target_search_volume.isnot(None), ins.excluded.target_search_volume_source),
                    else_=tbl.c.target_search_volume_source,
                ),
                "keywords_search_volume": func.coalesce(ins.excluded.keywords_search_volume, tbl.c.keywords_search_volume),
                "keywords_search_volume_source": case(
                    (ins.excluded.keywords_search_volume.isnot(None), ins.excluded.keywords_search_volume_source),
                    else_=tbl.c.keywords_search_volume_source,
                ),
                "last_success_at": ins.excluded.last_success_at,
                "last_error": ins.excluded.last_error,
                "is_stale": ins.excluded.is_stale,
                "updated_at": now,
            },
        )
        db.execute(stmt)
        return

    row = db.scalar(
        select(EntityDailyMetric).where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date == metric_date,
        )
    )
    if row is None:
        row = EntityDailyMetric(
            entity_id=entity_id,
            metric_date=metric_date,
            target_search_volume=target_volume if set_target else None,
            target_search_volume_source="google_trends" if set_target else None,
            keywords_search_volume=keywords_volume if set_keywords else None,
            keywords_search_volume_source="google_trends" if set_keywords else None,
            last_success_at=now,
            last_error=None,
            is_stale=False,
        )
        db.add(row)
    else:
        if set_target:
            row.target_search_volume = target_volume
            row.target_search_volume_source = "google_trends"
        if set_keywords:
            row.keywords_search_volume = keywords_volume
            row.keywords_search_volume_source = "google_trends"
        row.last_success_at = now
        row.last_error = None
        row.is_stale = False


def _upsert_search_volumes_unavailable(
    db: Session,
    entity_id: uuid.UUID,
    metric_date: date,
    now: datetime,
) -> None:
    """Mark failed fetch without wiping prior successful target or keywords values."""
    if _is_postgres(db):
        tbl = EntityDailyMetric.__table__
        ins = pg_insert(EntityDailyMetric).values(
            id=uuid.uuid4(),
            entity_id=entity_id,
            metric_date=metric_date,
            target_search_volume=None,
            target_search_volume_source="unavailable",
            keywords_search_volume=None,
            keywords_search_volume_source="unavailable",
            search_trend=None,
            search_trend_source=None,
            coverage_volume=None,
            sentiment_score=None,
            coverage_volume_source=None,
            last_success_at=None,
            last_error="pytrends_unavailable",
            is_stale=True,
            extra=None,
        )
        stmt = ins.on_conflict_do_update(
            constraint="uq_entity_daily_metric_day",
            set_={
                "target_search_volume": case(
                    (
                        and_(
                            tbl.c.target_search_volume_source.in_(list(_GOOGLE)),
                            tbl.c.target_search_volume.isnot(None),
                        ),
                        tbl.c.target_search_volume,
                    ),
                    else_=ins.excluded.target_search_volume,
                ),
                "target_search_volume_source": case(
                    (
                        or_(tbl.c.target_search_volume_source.is_(None), tbl.c.target_search_volume_source == ""),
                        ins.excluded.target_search_volume_source,
                    ),
                    else_=tbl.c.target_search_volume_source,
                ),
                "keywords_search_volume": case(
                    (
                        and_(
                            tbl.c.keywords_search_volume_source.in_(list(_GOOGLE)),
                            tbl.c.keywords_search_volume.isnot(None),
                        ),
                        tbl.c.keywords_search_volume,
                    ),
                    else_=ins.excluded.keywords_search_volume,
                ),
                "keywords_search_volume_source": case(
                    (
                        or_(tbl.c.keywords_search_volume_source.is_(None), tbl.c.keywords_search_volume_source == ""),
                        ins.excluded.keywords_search_volume_source,
                    ),
                    else_=tbl.c.keywords_search_volume_source,
                ),
                "last_error": func.coalesce(tbl.c.last_error, ins.excluded.last_error),
                "is_stale": ins.excluded.is_stale,
                "updated_at": now,
            },
        )
        db.execute(stmt)
        return

    row = db.scalar(
        select(EntityDailyMetric).where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date == metric_date,
        )
    )
    if row is None:
        db.add(
            EntityDailyMetric(
                entity_id=entity_id,
                metric_date=metric_date,
                target_search_volume=None,
                target_search_volume_source="unavailable",
                keywords_search_volume=None,
                keywords_search_volume_source="unavailable",
                last_success_at=None,
                last_error="pytrends_unavailable",
                is_stale=True,
            )
        )
    else:
        row.last_error = row.last_error or "pytrends_unavailable"
        row.is_stale = True
        if not row.target_search_volume_source:
            row.target_search_volume_source = "unavailable"
        if not row.keywords_search_volume_source:
            row.keywords_search_volume_source = "unavailable"


def sync_entity_search_trend(
    db: Session,
    entity_id: uuid.UUID,
    *,
    timeframe: str | None = None,
) -> int:
    """
    Pull Google Trends per keyword (one request each). Writes:
    - target_search_volume: primary instrument symbol only
    - keywords_search_volume: sum of independent narrative keyword series per day
    UPSERT on (entity_id, metric_date). No merged / averaged cross-tool value.
    """
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == entity_id).options(selectinload(PortfolioEntity.terms), selectinload(PortfolioEntity.instrument))
    )
    if not entity:
        return 0
    target_kw, narrative_kws = entity_target_and_narrative_keywords(entity)
    if not target_kw and not narrative_kws:
        return 0
    if not pytrends_enabled(db):
        return 0

    tf = normalize_trends_timeframe(timeframe)

    target_by_date: dict[date, float] = {}
    if target_kw:
        for p in get_daily_interest_single_keyword(target_kw, tf):
            try:
                d = date.fromisoformat(str(p["date"]))
                target_by_date[d] = float(p["value"])
            except Exception:
                continue

    keywords_by_date: dict[date, float] = defaultdict(float)
    for nk in narrative_kws:
        for p in get_daily_interest_single_keyword(nk, tf):
            try:
                d = date.fromisoformat(str(p["date"]))
                keywords_by_date[d] += float(p["value"])
            except Exception:
                continue

    has_target_data = bool(target_by_date)
    has_kw_data = bool(keywords_by_date)

    if not has_target_data and not has_kw_data:
        now = utcnow()
        _upsert_search_volumes_unavailable(db, entity_id, date.today(), now)
        logger.warning(
            "pytrends no series entity_id=%s target=%s narrative_n=%s timeframe=%s",
            entity_id,
            bool(target_kw),
            len(narrative_kws),
            tf,
        )
        return 0

    now = utcnow()
    all_dates = sorted(set(target_by_date.keys()) | set(keywords_by_date.keys()))
    n = 0
    for d in all_dates:
        set_t = bool(target_kw) and d in target_by_date
        set_k = bool(narrative_kws) and d in keywords_by_date
        tv = target_by_date.get(d) if set_t else None
        kv = keywords_by_date.get(d) if set_k else None
        _upsert_search_volumes_success(
            db,
            entity_id,
            d,
            now,
            target_volume=tv,
            set_target=set_t,
            keywords_volume=kv,
            set_keywords=set_k,
        )
        n += 1
    return n


def get_chart_3d_payload(
    db: Session,
    entity_id: uuid.UUID,
    range_key: str,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    """Keywords search (y) + coverage (x) only; no target-search mix."""
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
    out: list[dict[str, float | str]] = []
    k_src = "unavailable"
    has_real_cov = False

    for d in date_list:
        br = by_db.get(d)
        if br is None or br.keywords_search_volume is None:
            continue
        src = (br.keywords_search_volume_source or "").strip().lower()
        if src not in {"google_trends", "real"}:
            continue
        k_val = float(br.keywords_search_volume)
        k_src = "real"

        day_date = date.fromisoformat(d)
        if br.coverage_volume is not None and (br.coverage_volume_source or "").strip().lower() == "real":
            cv = float(br.coverage_volume)
            has_real_cov = True
        else:
            cov_db = coverage_from_deduped_docs(db, entity_id, day_date)
            if cov_db is not None:
                cv = float(cov_db)
                has_real_cov = True
            else:
                continue

        out.append({"date": d, "keywords_search_volume": k_val, "coverage_volume": cv})

    cv_src = "real" if has_real_cov else "unavailable"

    return out, {"keywords_search_volume": k_src or "unavailable", "coverage_volume": cv_src or "unavailable"}


def get_entity_keywords_search_timeseries(
    db: Session,
    entity_id: uuid.UUID,
    range_key: str,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    rk = normalize_chart_3d_range(range_key)
    days = _CHART3D_RANGE_DAYS[rk]
    start_day = date.today() - timedelta(days=days + 2)
    rows = db.scalars(
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= start_day,
            EntityDailyMetric.keywords_search_volume.isnot(None),
            EntityDailyMetric.keywords_search_volume_source.in_(list(_GOOGLE)),
        )
        .order_by(EntityDailyMetric.metric_date)
    ).all()
    series = [{"date": r.metric_date.isoformat(), "keywords_search_volume": float(r.keywords_search_volume)} for r in rows]
    st_src = "real" if rows else "unavailable"
    return series, {"keywords_search_volume": st_src}


def get_entity_target_search_timeseries(
    db: Session,
    entity_id: uuid.UUID,
    range_key: str,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    rk = normalize_chart_3d_range(range_key)
    days = _CHART3D_RANGE_DAYS[rk]
    start_day = date.today() - timedelta(days=days + 2)
    rows = db.scalars(
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= start_day,
            EntityDailyMetric.target_search_volume.isnot(None),
            EntityDailyMetric.target_search_volume_source.in_(list(_GOOGLE)),
        )
        .order_by(EntityDailyMetric.metric_date)
    ).all()
    series = [{"date": r.metric_date.isoformat(), "target_search_volume": float(r.target_search_volume)} for r in rows]
    st_src = "real" if rows else "unavailable"
    return series, {"target_search_volume": st_src}


def get_entity_search_trend_timeseries(
    db: Session,
    entity_id: uuid.UUID,
    terms: list[str],
    range_key: str,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    _ = terms
    return get_entity_keywords_search_timeseries(db, entity_id, range_key)
