from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import feedparser
import redis
from croniter import croniter

from app.core.platform_tz import now_platform
from app.core.config import settings
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.ai_access import (
    AI_BACKGROUND_SKIP_DETAIL,
    AI_RUN_SKIP_REASON_CODE,
    AI_SCHEDULE_TYPES,
)
from app.core.feature_access import can_access_feature, feature_key_for_schedule_type
from app.db.session import SessionLocal
from app.models.index_point import IndexPoint
from app.models.keyword_group import KeywordGroup
from app.models.macro_event import MacroEvent
from app.models.monitoring import MonitoringRun, MonitoringSchedule
from app.models.portfolio import PortfolioEntity
from app.models.user import User
from app.models.report import Report
from app.services.analysis import (
    analyze_documents_for_group,
    compute_derivatives,
    floor_time_bucket,
)
from app.services.ai.service import analyze_documents
from app.services.ingest_rss import ingest_rss_for_group
from app.services.reporting import (
    build_daily_info_report_markdown,
    build_entity_snapshot_markdown,
    build_group_snapshot_markdown,
)
from app.services.spikes import detect_and_store_spikes
from app.services.entity_metrics_pipeline import sync_entity_search_trend
from app.services.massive_analysis_pipeline import (
    run_massive_light_analysis_for_entity,
    select_light_entity_candidates,
)
from app.services.massive_backfill_queue import pick_pending_backfill_rows
from app.services.massive_guard import massive_paused
from app.services.runtime_flags import RuntimeFlagKey, get_flag, provider_enabled, pytrends_enabled
from app.services.runtime_logs import append_runtime_log
from app.services.news_normalization_pipeline import pick_entity_candidates, upsert_normalized_news_for_entity
from app.services.massive_repair_scan import (
    acquire_massive_repair_scan_lock,
    release_massive_repair_scan_lock,
    repair_scan_offhours_cooldown_blocks_after_lock,
    repair_scan_should_execute_tick,
    run_massive_market_repair_scan,
)
from app.services.market_snapshots import (
    OHLCV_CACHE_PERIODS,
    collect_symbols_for_scheduled_market_refresh,
    refresh_ohlcv_batch_with_fallback,
    refresh_quotes_batch_with_fallback,
    upsert_ohlcv_1m_twelve_warm,
    upsert_ohlcv_from_fetch,
    upsert_quote_from_fetch,
    upsert_quote_twelve_warm,
)
from app.services.triple_signal_metrics import upsert_entity_triple_signal_metrics
from app.worker.celery_app import celery_app
from app.models.data_subscription import UserDataSubscription
from app.services.subscriptions import ensure_subscription

logger = logging.getLogger(__name__)

# Limits Yahoo/Stooq burst when Celery falls back (Twelve-primary symbols skip Yahoo entirely).
_MARKET_REFRESH_BATCH_SIZE = 3
_MARKET_REFRESH_INTER_BATCH_SLEEP_SEC = 2.0
_MASSIVE_LIGHT_ENTITY_LIMIT = 20
MASSIVE_BACKFILL_BATCH_SIZE = 5
_TASK_GUARD_PREFIX = "market:v1:task_guard:"
_PRIMARY_MARKET_QUOTES_TS = "market:v1:refresh_market_quotes:last_run_ts"
_INPROC_GUARD: dict[str, float] = {}


def _rtlog(
    db: SessionLocal,
    *,
    level: str = "info",
    category: str = "job",
    job_name: str,
    provider: str | None = None,
    status: str | None = None,
    message: str,
    disabled_by_runtime_flag: bool = False,
    no_provider_call: bool = False,
    request_count: int | None = None,
    fallback_count: int | None = None,
    symbol_count: int | None = None,
) -> None:
    append_runtime_log(
        db,
        level=level,
        category=category,
        job_name=job_name,
        provider=provider,
        status=status,
        message=message,
        disabled_by_runtime_flag=disabled_by_runtime_flag,
        no_provider_call=no_provider_call,
        request_count=request_count,
        fallback_count=fallback_count,
        symbol_count=symbol_count,
    )


def _symbol_batches(symbols: list[str], batch_size: int = _MARKET_REFRESH_BATCH_SIZE) -> list[list[str]]:
    if not symbols:
        return []
    return [symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)]


def _tasks_r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _task_guard_seconds() -> int:
    return int(max(0, int(getattr(settings, "twelve_task_guard_seconds", 45))))


def _skip_after_primary_seconds() -> int:
    return int(max(0, int(getattr(settings, "twelve_secondary_skip_after_primary_seconds", 300))))


def _acquire_task_guard(task_name: str, min_seconds: int) -> bool:
    """Best-effort run gate. True = run now, False = skip (recently started)."""
    if min_seconds <= 0:
        return True
    key = f"{_TASK_GUARD_PREFIX}{task_name}"
    ttl = max(5, int(min_seconds))
    try:
        ok = bool(_tasks_r().set(key, "1", nx=True, ex=ttl))
        return ok
    except Exception:
        now = time.time()
        last = float(_INPROC_GUARD.get(key) or 0.0)
        if last and (now - last) < float(min_seconds):
            return False
        _INPROC_GUARD[key] = now
        return True


def _mark_primary_market_quotes_run() -> None:
    now = time.time()
    ttl = max(120, _skip_after_primary_seconds() * 2)
    try:
        _tasks_r().set(_PRIMARY_MARKET_QUOTES_TS, str(now), ex=ttl)
    except Exception:
        _INPROC_GUARD[_PRIMARY_MARKET_QUOTES_TS] = now


def _primary_market_quotes_recent(max_age_seconds: int) -> bool:
    if max_age_seconds <= 0:
        return False
    now = time.time()
    try:
        raw = _tasks_r().get(_PRIMARY_MARKET_QUOTES_TS)
        if not raw:
            return False
        return (now - float(raw)) < float(max_age_seconds)
    except Exception:
        last = float(_INPROC_GUARD.get(_PRIMARY_MARKET_QUOTES_TS) or 0.0)
        if not last:
            return False
        return (now - last) < float(max_age_seconds)


def _refresh_market_snapshots_sync(symbols: list[str], *, ohlcv_periods: tuple[str, ...] | None = None) -> dict:
    """
    Run quote + OHLCV upserts for the given symbols (used by Celery tasks only).
    Commits quotes then OHLCV in separate transactions.
    """
    syms = sorted({(s or "").strip().upper() for s in (symbols or []) if (s or "").strip()})
    if not syms:
        return {"symbols": [], "quotes_attempted": 0, "ohlcv_cells": 0}
    periods = ohlcv_periods if ohlcv_periods is not None else OHLCV_CACHE_PERIODS
    q_ok = 0
    with SessionLocal() as db:
        stats = refresh_quotes_batch_with_fallback(db, syms, max_chunks_per_run=5)
        q_ok = int(stats.get("success_count") or 0)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("_refresh_market_snapshots_sync quote batch commit failed")
    cells = 0
    with SessionLocal() as db:
        stats = refresh_ohlcv_batch_with_fallback(db, syms, periods=periods)
        cells = int(stats.get("success_count") or 0)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("_refresh_market_snapshots_sync ohlcv batch commit failed")
    return {"symbols": syms, "quotes_attempted": q_ok, "ohlcv_cells": cells}


def _enforce_report_limit(db: SessionLocal, user_id: uuid.UUID, max_reports: int | None = None) -> None:
    """
    Keep only the newest max_reports reports for a user, deleting older ones.
    Uses FREE_PLAN limit when max_reports not specified.
    """
    from app.core.limits import MAX_REPORTS
    if max_reports is None:
        max_reports = MAX_REPORTS
    subq = (
        select(Report.id)
        .where(Report.user_id == user_id)
        .order_by(Report.created_at.desc())
        .offset(max_reports)
    )
    old_ids = [rid for (rid,) in db.execute(subq).all()]
    if not old_ids:
        return
    db.execute(delete(Report).where(Report.id.in_(old_ids)))
    db.commit()


@celery_app.task(name="app.worker.tasks.tick_schedules")
def tick_schedules() -> dict:
    now = now_platform()
    triggered = 0

    with SessionLocal() as db:
        schedules = db.scalars(
            select(MonitoringSchedule).where(
                MonitoringSchedule.is_active.is_(True),
                MonitoringSchedule.status == "active",
            )
        ).all()
        for s in schedules:
            last = s.last_triggered_at
            itr = croniter(s.cron, now)
            prev_occurrence: datetime = itr.get_prev(datetime)
            due = last is None or prev_occurrence > last
            if not due:
                continue
            s.last_triggered_at = now
            db.add(s)
            db.commit()
            trigger_monitoring_run.delay(user_id=str(s.user_id), schedule_id=str(s.id))
            triggered += 1

    return {"triggered": triggered}


@celery_app.task(name="app.worker.tasks.trigger_monitoring_run")
def trigger_monitoring_run(*, user_id: str, schedule_id: str | None = None) -> dict:
    # Ensure schema has entity_ids_csv so worker does not crash on existing DBs
    from app.db.session import engine
    from app.db.schema_patch import run_schema_patches
    run_schema_patches(engine)

    uid = uuid.UUID(user_id)
    sid = uuid.UUID(schedule_id) if schedule_id else None
    now = now_platform()

    with SessionLocal() as db:
        run = MonitoringRun(user_id=uid, schedule_id=sid, status="running", started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            if sid:
                schedule = db.get(MonitoringSchedule, sid)
                group_ids = [uuid.UUID(x) for x in (schedule.group_ids_csv or "").split(",") if x.strip()]
                entity_ids = [uuid.UUID(x) for x in (getattr(schedule, "entity_ids_csv", None) or "").split(",") if x.strip()]
                bucket_minutes = schedule.bucket_minutes
                stype = getattr(schedule, "schedule_type", None) or "standard_monitor"
            else:
                schedule = None
                group_ids = []
                entity_ids = []
                bucket_minutes = 60
                stype = "standard_monitor"

            owner = db.get(User, uid)
            if stype in AI_SCHEDULE_TYPES:
                if not owner or not can_access_feature(owner, feature_key_for_schedule_type(stype)):
                    run.status = "success"
                    run.finished_at = now_platform()
                    run.detail = AI_BACKGROUND_SKIP_DETAIL
                    db.add(run)
                    db.commit()
                    _rtlog(
                        db,
                        category="ai",
                        job_name="trigger_monitoring_run",
                        provider=None,
                        status="skipped",
                        message=f"entitlement_denied schedule_type={stype}",
                        disabled_by_runtime_flag=False,
                        no_provider_call=True,
                        request_count=0,
                    )
                    return {"run_id": str(run.id), "skipped": True, "reason": AI_RUN_SKIP_REASON_CODE}
                # Runtime flags: skip AI schedules early with clear detail (no provider call attempted).
                from app.services.runtime_flags import RuntimeFlagKey, ai_feature_enabled

                if stype == "ai_alert" and not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_ALERTS):
                    run.status = "success"
                    run.finished_at = now_platform()
                    run.detail = "disabled_by_runtime_flag:ENABLE_AI_ALERTS"
                    db.add(run)
                    db.commit()
                    logger.info(
                        "job=trigger_monitoring_run schedule_type=%s disabled_by_runtime_flag=1 ai_feature_flag=%s no_provider_call=true",
                        stype,
                        RuntimeFlagKey.ENABLE_AI_ALERTS,
                    )
                    _rtlog(
                        db,
                        category="ai",
                        job_name="trigger_monitoring_run",
                        provider=None,
                        status="skipped",
                        message=f"disabled_by_runtime_flag schedule_type={stype}",
                        disabled_by_runtime_flag=True,
                        no_provider_call=True,
                        request_count=0,
                    )
                    return {"run_id": str(run.id), "skipped": True, "reason": "disabled_by_runtime_flag"}
                if stype == "ai_report" and not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_REPORT_GENERATION):
                    run.status = "success"
                    run.finished_at = now_platform()
                    run.detail = "disabled_by_runtime_flag:ENABLE_AI_REPORT_GENERATION"
                    db.add(run)
                    db.commit()
                    logger.info(
                        "job=trigger_monitoring_run schedule_type=%s disabled_by_runtime_flag=1 ai_feature_flag=%s no_provider_call=true",
                        stype,
                        RuntimeFlagKey.ENABLE_AI_REPORT_GENERATION,
                    )
                    _rtlog(
                        db,
                        category="ai",
                        job_name="trigger_monitoring_run",
                        provider=None,
                        status="skipped",
                        message=f"disabled_by_runtime_flag schedule_type={stype}",
                        disabled_by_runtime_flag=True,
                        no_provider_call=True,
                        request_count=0,
                    )
                    return {"run_id": str(run.id), "skipped": True, "reason": "disabled_by_runtime_flag"}

            # AI Alert / AI Report / General Alert: use simplified pipeline
            if stype in ("ai_alert", "ai_report", "general_alert"):
                from app.services.ai_alert import run_ai_alert_pipeline, run_ai_report_pipeline

                linked = [x for x in (getattr(schedule, "linked_assets_csv", None) or "").split(",") if x.strip()]
                thr = getattr(schedule, "impact_threshold", None)
                lbl = getattr(schedule, "label", None)

                if stype == "ai_report":
                    out = run_ai_report_pipeline(
                        db=db, user_id=uid, schedule_id=sid, schedule_type=stype,
                        group_ids=group_ids, entity_ids=entity_ids, linked_assets=linked, label=lbl,
                    )
                    _enforce_report_limit(db, uid)
                else:
                    out = run_ai_alert_pipeline(
                        db=db, user_id=uid, schedule_id=sid, schedule_type=stype,
                        group_ids=group_ids, entity_ids=entity_ids, linked_assets=linked,
                        threshold=thr, label=lbl,
                    )

                run.status = "success"
                run.finished_at = now_platform()
                run.detail = str(out)
                db.add(run)
                db.commit()
                return {"run_id": str(run.id), **out}

            # Entity-based run: generate entity_snapshot reports only (no IndexPoint / RSS)
            if entity_ids:
                bucket_start = floor_time_bucket(now, bucket_minutes=bucket_minutes)
                window_start = bucket_start
                window_end = bucket_start + timedelta(minutes=bucket_minutes)
                reports_created = 0
                for eid in entity_ids:
                    entity = db.scalar(
                        select(PortfolioEntity)
                        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == uid)
                        .options(
                            selectinload(PortfolioEntity.portfolio),
                            selectinload(PortfolioEntity.instrument),
                            selectinload(PortfolioEntity.terms),
                        )
                    )
                    if not entity:
                        continue
                    portfolio_name = entity.portfolio.name if entity.portfolio else "—"
                    md = build_entity_snapshot_markdown(
                        entity=entity,
                        portfolio_name=portfolio_name,
                        window_start=window_start,
                        window_end=window_end,
                    )
                    inst = entity.instrument
                    report = Report(
                        user_id=uid,
                        kind="entity_snapshot",
                        title=f"{entity.name} - Entity snapshot",
                        body_markdown=md,
                        payload={
                            "entity_id": str(entity.id),
                            "entity_name": entity.name,
                            "portfolio_name": portfolio_name,
                            "instrument": inst.symbol if inst else None,
                            "asset_type": inst.asset_class if inst else None,
                            "terms": [t.term for t in entity.terms],
                            "sentiment": None,
                            "coverage_volume": None,
                            "coverage_momentum": None,
                            "coverage_acceleration": None,
                            "bucket_start": bucket_start.isoformat(),
                        },
                        window_start=window_start,
                        window_end=window_end,
                    )
                    db.add(report)
                    db.commit()
                    _enforce_report_limit(db, uid)
                    reports_created += 1
                run.status = "success"
                run.finished_at = now_platform()
                run.detail = f"entity_snapshot_reports={reports_created}"
                db.add(run)
                db.commit()
                return {
                    "run_id": str(run.id),
                    "entity_snapshot_reports": reports_created,
                }

            # 1) Ingest
            ingested_docs = 0
            ingested_links = 0
            analyzed = 0

            # 2) Analyze groups
            if not group_ids:
                group_ids = db.scalars(
                    select(KeywordGroup.id).where(KeywordGroup.user_id == uid, KeywordGroup.is_active.is_(True))
                ).all()

            bucket_start = floor_time_bucket(now, bucket_minutes=bucket_minutes)
            window_start = bucket_start
            window_end = bucket_start + timedelta(minutes=bucket_minutes)

            updated_points = 0
            for gid in group_ids:
                group = db.scalar(select(KeywordGroup).where(KeywordGroup.id == gid, KeywordGroup.user_id == uid))
                if not group:
                    continue

                # ingest RSS for this group
                dc, lc, newly_linked = ingest_rss_for_group(db=db, user_id=uid, group=group, lookback_hours=48)
                ingested_docs += dc
                ingested_links += lc

                # AI analyze newly linked docs (pluggable provider; heuristic fallback)
                analyzed += analyze_documents(
                    db=db, group_id=gid, document_ids=newly_linked, acting_user_id=uid
                )

                metrics, top_docs = analyze_documents_for_group(
                    db=db,
                    user_id=uid,
                    group=group,
                    window_start=window_start,
                    window_end=window_end,
                )

                point = db.scalar(
                    select(IndexPoint).where(IndexPoint.group_id == gid, IndexPoint.bucket_start == bucket_start)
                )
                if not point:
                    point = IndexPoint(group_id=gid, bucket_start=bucket_start, bucket_minutes=bucket_minutes)

                point.mention_volume = metrics["mention_volume"]
                point.sentiment_positive = metrics["pos"]
                point.sentiment_negative = metrics["neg"]
                point.sentiment_neutral = metrics["neu"]

                # compute momentum/d1/d2 based on previous point
                prev = db.scalar(
                    select(IndexPoint)
                    .where(IndexPoint.group_id == gid, IndexPoint.bucket_start < bucket_start)
                    .order_by(IndexPoint.bucket_start.desc())
                    .limit(1)
                )
                point.momentum, point.d1, point.d2 = compute_derivatives(current=point, previous=prev)

                db.add(point)
                db.commit()
                updated_points += 1

                # spike detection (persist for later overlays/alerts)
                detect_and_store_spikes(db=db, group_id=gid, point=point, prev=prev)

                # 3) Generate a lightweight narrative report snapshot
                md = build_group_snapshot_markdown(
                    db=db, group=group, window_start=window_start, window_end=window_end, docs=top_docs
                )
                report = Report(
                    user_id=uid,
                    kind="group_snapshot",
                    title=f"{group.name} - Narrative snapshot",
                    body_markdown=md,
                    payload={"group_id": str(group.id), "bucket_start": bucket_start.isoformat()},
                    window_start=window_start,
                    window_end=window_end,
                )
                db.add(report)
                db.commit()
                _enforce_report_limit(db, uid)

            run.status = "success"
            run.finished_at = now_platform()
            run.detail = (
                f"rss_docs_created={ingested_docs} group_links_created={ingested_links} "
                f"analyses_created={analyzed} index_points_upserted={updated_points}"
            )
            db.add(run)
            db.commit()

            return {
                "run_id": str(run.id),
                "rss_docs_created": ingested_docs,
                "group_links_created": ingested_links,
                "analyses_created": analyzed,
                "index_points": updated_points,
            }
        except Exception as e:  # noqa: BLE001
            run.status = "fail"
            run.finished_at = now_platform()
            run.detail = str(e)
            db.add(run)
            db.commit()
            raise


@celery_app.task(name="app.worker.tasks.generate_daily_reports")
def generate_daily_reports() -> dict:
    """
    Generates two user-level reports:
    - keyword_daily: placeholder (to be expanded with per-group summaries)
    - info_24h: most recent ingested documents for the user
    """
    from sqlalchemy import and_
    from app.models.user import User
    from app.models.document import SourceDocument

    now = now_platform()
    window_start = now - timedelta(hours=24)
    created = 0

    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        for u in users:
            docs = db.scalars(
                select(SourceDocument)
                .where(and_(SourceDocument.user_id == u.id, SourceDocument.published_at.is_not(None), SourceDocument.published_at >= window_start))
                .order_by(SourceDocument.published_at.desc())
                .limit(50)
            ).all()
            md = build_daily_info_report_markdown(items=docs)
            report = Report(
                user_id=u.id,
                kind="info_24h",
                title="24 Hour Information Report",
                body_markdown=md,
                payload={"window_hours": 24},
                window_start=window_start,
                window_end=now,
            )
            db.add(report)
            db.commit()
            _enforce_report_limit(db, u.id)
            created += 1

    return {"created": created}


MACRO_NEWS_FEEDS = [
    ("https://feeds.reuters.com/reuters/businessNews", "Reuters Business"),
    ("https://feeds.bloomberg.com/markets/news.rss", "Bloomberg Markets"),
    ("https://www.ft.com/?format=rss", "Financial Times World"),
]


@celery_app.task(name="app.worker.tasks.refresh_macro_news_list_snapshots")
def refresh_macro_news_list_snapshots() -> dict:
    """
    Pre-build Google News aggregate per macro category into macro_news_list_snapshots.
    Keeps GET /macro/news fast (cache-first).
    """
    from app.services.macro_news_snapshot import rebuild_snapshots_all_categories

    with SessionLocal() as db:
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_FETCH_MACRO_NEWS):
            logger.info("job=refresh_macro_news_list_snapshots disabled_by_runtime_flag=1")
            _rtlog(
                db,
                category="job",
                job_name="refresh_macro_news_list_snapshots",
                provider="macro_news",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"disabled_by_runtime_flag": True, "snapshot_counts": {}}
        counts = rebuild_snapshots_all_categories(db)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh_macro_news_list_snapshots commit failed")
            raise
        _rtlog(
            db,
            category="job",
            job_name="refresh_macro_news_list_snapshots",
            provider="macro_news",
            status="success",
            message=f"snapshots={sum(int(v or 0) for v in (counts or {}).values())}",
            no_provider_call=False,
        )
    return {"snapshot_counts": counts}


@celery_app.task(name="app.worker.tasks.fetch_macro_news")
def fetch_macro_news() -> dict:
    """
    Ingest macro news from RSS feeds into macro_events.
    Runs every 15 minutes via beat. Deduplicates by title.
    """
    inserted = 0
    with SessionLocal() as db:
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_FETCH_MACRO_NEWS):
            logger.info("job=fetch_macro_news disabled_by_runtime_flag=1")
            _rtlog(
                db,
                category="job",
                job_name="fetch_macro_news",
                provider="rss",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"disabled_by_runtime_flag": True, "inserted": 0}
        for feed_url, source_name in MACRO_NEWS_FEEDS:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as e:
                continue
            for entry in parsed.entries[:100]:
                title = (getattr(entry, "title", None) or "").strip()
                if not title or len(title) > 500:
                    continue
                published = None
                if getattr(entry, "published_parsed", None):
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except (TypeError, IndexError):
                        pass
                if not published:
                    published = datetime.now(timezone.utc)
                exists = db.scalar(select(MacroEvent.id).where(MacroEvent.title == title))
                if exists:
                    continue
                evt = MacroEvent(
                    user_id=None,
                    category="general",
                    title=title[:500],
                    source=source_name,
                    timestamp=published,
                    sentiment=None,
                    importance_score=None,
                )
                db.add(evt)
                db.commit()
                inserted += 1
        _rtlog(
            db,
            category="job",
            job_name="fetch_macro_news",
            provider="rss",
            status="success",
            message=f"inserted={inserted}",
            request_count=len(MACRO_NEWS_FEEDS),
            symbol_count=None,
        )
    return {"inserted": inserted}


@celery_app.task(name="app.worker.tasks.warm_pool_twelve_quotes")
def warm_pool_twelve_quotes() -> dict:
    """
    Fixed Twelve warm pool: quote refresh only (twelve_get_quote + snapshot merge + Redis via client).
    """
    from app.services.twelve_warm_pool import TWELVE_WARM_POOL_SYMBOLS

    t0 = time.perf_counter()
    logger.info("warm_pool started scope=quotes count=%s", len(TWELVE_WARM_POOL_SYMBOLS))
    with SessionLocal() as db:
        if not _acquire_task_guard("warm_pool_twelve_quotes", _task_guard_seconds()):
            _rtlog(
                db,
                category="provider",
                job_name="warm_pool_twelve_quotes",
                provider="market_chain",
                status="skipped",
                message="recent_run_guard",
                no_provider_call=True,
                request_count=0,
            )
            return {"skipped": True, "reason": "recent_run_guard"}
        if _primary_market_quotes_recent(_skip_after_primary_seconds()):
            _rtlog(
                db,
                category="provider",
                job_name="warm_pool_twelve_quotes",
                provider="market_chain",
                status="skipped",
                message="recent_primary_refresh",
                no_provider_call=True,
                request_count=0,
            )
            return {"skipped": True, "reason": "recent_primary_refresh"}
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_TWELVE_QUOTES):
            logger.info(
                "job=warm_pool_quotes disabled_by_runtime_flag=1 runtime_flag_checked=%s runtime_flag_value=false provider_call_attempted=false next_natural_run_unchanged=true",
                RuntimeFlagKey.ENABLE_TWELVE_QUOTES,
            )
            _rtlog(
                db,
                category="provider",
                job_name="warm_pool_twelve_quotes",
                provider="twelve",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
                symbol_count=len(TWELVE_WARM_POOL_SYMBOLS),
            )
            return {"disabled_by_runtime_flag": True, "flag": RuntimeFlagKey.ENABLE_TWELVE_QUOTES}
        stats = refresh_quotes_batch_with_fallback(db, list(TWELVE_WARM_POOL_SYMBOLS), max_chunks_per_run=5)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("warm_pool quotes commit failed")
            raise
        _rtlog(
            db,
            category="provider",
            job_name="warm_pool_twelve_quotes",
            provider="market_chain",
            status="success" if int(stats.get("fail_count") or 0) == 0 else "failed",
            message="warm_pool_quotes_completed",
            request_count=int(stats.get("request_count") or 0),
            fallback_count=int(stats.get("fallback_count") or 0),
            symbol_count=int(stats.get("symbol_count") or 0),
        )
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=warm_pool_quotes provider=market_chain request_count=%s fallback_count=%s symbol_count=%s chunk_count=%s chunk_size=%s "
        "success_count=%s fail_count=%s elapsed_ms=%s",
        stats.get("request_count"),
        stats.get("fallback_count"),
        stats.get("symbol_count"),
        stats.get("chunk_count"),
        stats.get("chunk_size"),
        stats.get("success_count"),
        stats.get("fail_count"),
        dt,
    )
    return {"scope": "quotes", **stats, "elapsed_ms": dt}


@celery_app.task(name="app.worker.tasks.warm_pool_twelve_time_series_1m")
def warm_pool_twelve_time_series_1m() -> dict:
    """Fixed Twelve warm pool: 1M daily bars only (twelve_get_time_series + OhlcvSnapshot)."""
    from app.services.twelve_warm_pool import TWELVE_WARM_POOL_SYMBOLS

    logger.info("warm_pool started scope=time_series_1m count=%s", len(TWELVE_WARM_POOL_SYMBOLS))
    ok = skip = fail = 0
    with SessionLocal() as db:
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_TWELVE_OHLCV):
            logger.info(
                "job=warm_pool_time_series_1m disabled_by_runtime_flag=1 runtime_flag_checked=%s runtime_flag_value=false provider_call_attempted=false next_natural_run_unchanged=true",
                RuntimeFlagKey.ENABLE_TWELVE_OHLCV,
            )
            _rtlog(
                db,
                category="provider",
                job_name="warm_pool_twelve_time_series_1m",
                provider="twelve",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
                symbol_count=len(TWELVE_WARM_POOL_SYMBOLS),
            )
            return {
                "disabled_by_runtime_flag": True,
                "flag": RuntimeFlagKey.ENABLE_TWELVE_OHLCV,
                "scope": "time_series_1m",
                "ok": 0,
                "skip": 0,
                "fail": 0,
            }
        for sym in TWELVE_WARM_POOL_SYMBOLS:
            try:
                res = upsert_ohlcv_1m_twelve_warm(db, sym)
            except Exception:
                logger.warning("warm_pool fail symbol=%s part=time_series", sym, exc_info=True)
                fail += 1
                continue
            if res == "ok":
                ok += 1
                logger.info("warm_pool time_series refreshed symbol=%s", sym)
            elif res == "skip":
                skip += 1
                logger.info("warm_pool skip symbol=%s part=time_series reason=policy", sym)
            else:
                fail += 1
                logger.info("warm_pool fail symbol=%s part=time_series reason=twelve_miss_or_empty", sym)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("warm_pool time_series commit failed")
        _rtlog(
            db,
            category="provider",
            job_name="warm_pool_twelve_time_series_1m",
            provider="twelve",
            status="success" if fail == 0 else "failed",
            message=f"ok={ok} skip={skip} fail={fail}",
            request_count=len(TWELVE_WARM_POOL_SYMBOLS),
            symbol_count=len(TWELVE_WARM_POOL_SYMBOLS),
        )
    return {"scope": "time_series_1m", "ok": ok, "skip": skip, "fail": fail}


@celery_app.task(name="app.worker.tasks.refresh_active_pool_twelve_quotes")
def refresh_active_pool_twelve_quotes() -> dict:
    """Global active pool: quote refresh every 15m (excludes fixed warm-pool symbols)."""
    from app.services.active_market_pool_service import (
        disable_stale_active_pool_entries,
        list_enabled_active_pool_symbols_excluding_warm,
    )

    logger.info("active_pool refresh started scope=quotes")
    stale_n = 0
    with SessionLocal() as db:
        if not _acquire_task_guard("refresh_active_pool_twelve_quotes", _task_guard_seconds()):
            _rtlog(
                db,
                category="provider",
                job_name="refresh_active_pool_twelve_quotes",
                provider="market_chain",
                status="skipped",
                message="recent_run_guard",
                no_provider_call=True,
                request_count=0,
            )
            return {"skipped": True, "reason": "recent_run_guard"}
        if _primary_market_quotes_recent(_skip_after_primary_seconds()):
            _rtlog(
                db,
                category="provider",
                job_name="refresh_active_pool_twelve_quotes",
                provider="market_chain",
                status="skipped",
                message="recent_primary_refresh",
                no_provider_call=True,
                request_count=0,
            )
            return {"skipped": True, "reason": "recent_primary_refresh"}
        stale_n = disable_stale_active_pool_entries(db)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("active_pool stale disable commit failed")

    syms: list[str] = []
    with SessionLocal() as db:
        syms = list_enabled_active_pool_symbols_excluding_warm(db)

    t0 = time.perf_counter()
    with SessionLocal() as db:
        stats = refresh_quotes_batch_with_fallback(db, syms, max_chunks_per_run=5)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("active_pool quotes commit failed")
            raise
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=active_pool_quotes provider=market_chain request_count=%s fallback_count=%s symbol_count=%s chunk_count=%s chunk_size=%s "
        "success_count=%s fail_count=%s elapsed_ms=%s",
        stats.get("request_count"),
        stats.get("fallback_count"),
        stats.get("symbol_count"),
        stats.get("chunk_count"),
        stats.get("chunk_size"),
        stats.get("success_count"),
        stats.get("fail_count"),
        dt,
    )
    return {"scope": "active_quotes", "symbols": len(syms), "stale_disabled": stale_n, **stats, "elapsed_ms": dt}


@celery_app.task(name="app.worker.tasks.refresh_active_pool_twelve_time_series_1m")
def refresh_active_pool_twelve_time_series_1m() -> dict:
    """Global active pool: 1M Twelve time_series every 2h (excludes fixed warm-pool symbols)."""
    from app.services.active_market_pool_service import list_enabled_active_pool_symbols_excluding_warm

    logger.info("active_pool refresh started scope=time_series_1m")
    syms: list[str] = []
    with SessionLocal() as db:
        syms = list_enabled_active_pool_symbols_excluding_warm(db)
    ok = skip = fail = 0
    with SessionLocal() as db:
        for sym in syms:
            try:
                res = upsert_ohlcv_1m_twelve_warm(db, sym)
            except Exception:
                logger.warning("active_pool refresh time_series failed symbol=%s", sym, exc_info=True)
                fail += 1
                continue
            if res == "ok":
                ok += 1
            elif res == "skip":
                skip += 1
            else:
                fail += 1
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("active_pool time_series commit failed")
    return {"scope": "active_time_series_1m", "symbols": len(syms), "ok": ok, "skip": skip, "fail": fail}


@celery_app.task(name="app.worker.tasks.refresh_market_quotes")
def refresh_market_quotes() -> dict:
    """
    Refresh shared market_quote_snapshots: V1 core + default indices + market_quote subscriptions.
    GET /market/* reads snapshots only; failures keep prior cached values inside upsert.
    """
    t0 = time.perf_counter()
    with SessionLocal() as db:
        if not _acquire_task_guard("refresh_market_quotes", _task_guard_seconds()):
            _rtlog(
                db,
                category="provider",
                job_name="refresh_market_quotes",
                provider="market_chain",
                status="skipped",
                message="recent_run_guard",
                no_provider_call=True,
                request_count=0,
            )
            return {"skipped": True, "reason": "recent_run_guard"}
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS):
            logger.info(
                "job=refresh_market_quotes disabled_by_runtime_flag=1 runtime_flag_checked=%s runtime_flag_value=false provider_call_attempted=false next_natural_run_unchanged=true",
                RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS,
            )
            _rtlog(
                db,
                category="provider",
                job_name="refresh_market_quotes",
                provider="market_chain",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"disabled_by_runtime_flag": True, "flag": RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS}
        _mark_primary_market_quotes_run()
        syms_sorted = sorted(collect_symbols_for_scheduled_market_refresh(db))
        stats = refresh_quotes_batch_with_fallback(db, syms_sorted, max_chunks_per_run=5)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh_market_quotes commit failed")
            raise
        _rtlog(
            db,
            category="provider",
            job_name="refresh_market_quotes",
            provider="market_chain",
            status="success" if int(stats.get("fail_count") or 0) == 0 else "failed",
            message="refresh_market_quotes_completed",
            request_count=int(stats.get("request_count") or 0),
            fallback_count=int(stats.get("fallback_count") or 0),
            symbol_count=int(stats.get("symbol_count") or 0),
        )
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=refresh_market_quotes provider=market_chain request_count=%s fallback_count=%s symbol_count=%s chunk_count=%s chunk_size=%s "
        "success_count=%s fail_count=%s elapsed_ms=%s",
        stats.get("request_count"),
        stats.get("fallback_count"),
        stats.get("symbol_count"),
        stats.get("chunk_count"),
        stats.get("chunk_size"),
        stats.get("success_count"),
        stats.get("fail_count"),
        dt,
    )
    return {**stats, "elapsed_ms": dt}


@celery_app.task(name="app.worker.tasks.refresh_market_ohlcv_snapshots")
def refresh_market_ohlcv_snapshots() -> dict:
    """Periodic OHLCV snapshot fill (low frequency). Request handlers do not call providers."""
    t0 = time.perf_counter()
    with SessionLocal() as db:
        if not _acquire_task_guard("refresh_market_ohlcv_snapshots", _task_guard_seconds()):
            _rtlog(
                db,
                category="provider",
                job_name="refresh_market_ohlcv_snapshots",
                provider="market_chain",
                status="skipped",
                message="recent_run_guard",
                no_provider_call=True,
                request_count=0,
            )
            return {"skipped": True, "reason": "recent_run_guard"}
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS):
            logger.info(
                "job=refresh_market_ohlcv_snapshots disabled_by_runtime_flag=1 runtime_flag_checked=%s runtime_flag_value=false provider_call_attempted=false next_natural_run_unchanged=true",
                RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS,
            )
            _rtlog(
                db,
                category="provider",
                job_name="refresh_market_ohlcv_snapshots",
                provider="market_chain",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"disabled_by_runtime_flag": True, "flag": RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS}
        syms_sorted = sorted(collect_symbols_for_scheduled_market_refresh(db))
        stats = refresh_ohlcv_batch_with_fallback(db, syms_sorted, periods=OHLCV_CACHE_PERIODS)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh_market_ohlcv_snapshots commit failed")
            raise
        _rtlog(
            db,
            category="provider",
            job_name="refresh_market_ohlcv_snapshots",
            provider="market_chain",
            status="success" if int(stats.get("fail_count") or 0) == 0 else "failed",
            message="refresh_market_ohlcv_completed",
            request_count=int(stats.get("request_count") or 0),
            fallback_count=int(stats.get("fallback_count") or 0),
            symbol_count=int(stats.get("symbol_count") or 0),
        )
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=refresh_market_ohlcv_snapshots provider=market_chain request_count=%s fallback_count=%s symbol_count=%s chunk_count=%s chunk_size=%s "
        "success_count=%s fail_count=%s elapsed_ms=%s",
        stats.get("request_count"),
        stats.get("fallback_count"),
        stats.get("symbol_count"),
        stats.get("chunk_count"),
        stats.get("chunk_size"),
        stats.get("success_count"),
        stats.get("fail_count"),
        dt,
    )
    return {**stats, "elapsed_ms": dt}


@celery_app.task(name="app.worker.tasks.refresh_market_snapshots_for_symbols")
def refresh_market_snapshots_for_symbols(symbols: list[str]) -> dict:
    """Background: refresh quotes + full OHLCV cache for specific symbols (e.g. user-added index)."""
    return _refresh_market_snapshots_sync(symbols)


@celery_app.task(name="app.worker.tasks.refresh_core_market_cache_admin")
def refresh_core_market_cache_admin() -> dict:
    """Admin/dev: refresh quotes + OHLCV for V1 core shared symbols only."""
    from app.services.market_indices_config import CORE_SHARED_MARKET_SYMBOLS_V1

    return _refresh_market_snapshots_sync(sorted(CORE_SHARED_MARKET_SYMBOLS_V1))


@celery_app.task(name="app.worker.tasks.warmup_core_market_snapshots")
def warmup_core_market_snapshots() -> dict:
    """
    Post-deploy: staggered refresh for core symbols only (quotes + 1D/1M OHLCV).
    Full OHLCV periods remain on the 6h beat to limit external burst.
    """
    from app.services.market_indices_config import CORE_SHARED_MARKET_SYMBOLS_V1

    t0 = time.perf_counter()
    syms = sorted(CORE_SHARED_MARKET_SYMBOLS_V1)
    with SessionLocal() as db:
        stats_q = refresh_quotes_batch_with_fallback(db, syms, max_chunks_per_run=5)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("warmup_core_market_snapshots quote commit failed")
            raise

    lite_periods: tuple[str, ...] = ("1D", "1M")
    with SessionLocal() as db:
        stats_o = refresh_ohlcv_batch_with_fallback(db, syms, periods=lite_periods)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("warmup_core_market_snapshots ohlcv commit failed")
            raise
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=warmup_core_market_snapshots provider=market_chain "
        "quote_request_count=%s quote_fallback_count=%s ohlcv_request_count=%s ohlcv_fallback_count=%s "
        "symbol_count=%s elapsed_ms=%s",
        stats_q.get("request_count"),
        stats_q.get("fallback_count"),
        stats_o.get("request_count"),
        stats_o.get("fallback_count"),
        len(syms),
        dt,
    )
    return {"warmup": "core", "symbols": len(syms), "ohlcv_periods": list(lite_periods), "elapsed_ms": dt}


@celery_app.task(name="app.worker.tasks.sync_entity_daily_metrics")
def sync_entity_daily_metrics() -> dict:
    """Daily job: Google Trends → entity_daily_metrics target + keywords search volumes (pytrends, per keyword)."""
    total_rows = 0
    n_entities = 0
    invalid_subscriptions = 0
    orphan_subscriptions = 0
    repaired_subscriptions = 0
    with SessionLocal() as db:
        if not pytrends_enabled(db):
            logger.info("job=sync_entity_daily_metrics disabled_by_runtime_flag=ENABLE_PYTRENDS")
            _rtlog(
                db,
                category="job",
                job_name="sync_entity_daily_metrics",
                provider="pytrends",
                status="skipped",
                message="disabled_by_runtime_flag_ENABLE_PYTRENDS",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"disabled_by_runtime_flag": True, "entities": 0, "metric_rows": 0}
        subs = db.scalars(
            select(UserDataSubscription).where(
                UserDataSubscription.source_type == "search_trend",
                UserDataSubscription.is_active.is_(True),
                UserDataSubscription.target_type == "entity",
            )
        ).all()
        entity_ids: set[uuid.UUID] = set()
        for s in subs:
            try:
                entity_ids.add(uuid.UUID(s.target_id))
            except ValueError:
                db.delete(s)
                invalid_subscriptions += 1
                continue
        all_entities = db.scalars(select(PortfolioEntity).options(selectinload(PortfolioEntity.terms))).all()
        valid_entities: dict[uuid.UUID, PortfolioEntity] = {e.id: e for e in all_entities}
        # clean orphan subscriptions
        for s in subs:
            try:
                eid = uuid.UUID(s.target_id)
            except ValueError:
                continue
            if eid not in valid_entities:
                db.delete(s)
                orphan_subscriptions += 1
        # include active entities with terms even if subscriptions are missing/stale
        for e in all_entities:
            if e.terms:
                entity_ids.add(e.id)
                sub = ensure_subscription(
                    db,
                    user_id=e.user_id,
                    source_type="search_trend",
                    target_type="entity",
                    target_id=str(e.id),
                    frequency="daily",
                )
                if sub and sub.last_attempt_at is None:
                    repaired_subscriptions += 1

        for eid in sorted(entity_ids, key=lambda x: str(x)):
            entity = valid_entities.get(eid)
            if not entity:
                continue
            if not entity.terms:
                continue
            sub = db.scalar(
                select(UserDataSubscription).where(
                    UserDataSubscription.source_type == "search_trend",
                    UserDataSubscription.target_type == "entity",
                    UserDataSubscription.target_id == str(eid),
                )
            )
            extra = (sub.extra or {}) if sub else {}
            tf = extra.get("trends_timeframe") or extra.get("timeframe")
            rows = sync_entity_search_trend(db, eid, timeframe=tf)
            if rows == 0 and entity.terms:
                # Defensive guarantee: should not happen, but never silently skip valid-terms entities.
                rows = sync_entity_search_trend(db, eid, timeframe="today 3-m")
            total_rows += rows
            n_entities += 1
            logger.info("entity metrics synced entity_id=%s rows=%d timeframe=%s", eid, rows, tf or "default")
        db.commit()
        _rtlog(
            db,
            category="job",
            job_name="sync_entity_daily_metrics",
            provider="pytrends",
            status="success",
            message=f"entities={n_entities} metric_rows={total_rows}",
        )
    return {
        "entities": n_entities,
        "metric_rows": total_rows,
        "invalid_subscriptions_removed": invalid_subscriptions,
        "orphan_subscriptions_removed": orphan_subscriptions,
        "subscriptions_repaired": repaired_subscriptions,
    }


@celery_app.task(name="app.worker.tasks.refresh_normalized_entity_news")
def refresh_normalized_entity_news(max_entities: int = 20) -> dict:
    """
    Real news pipeline (minimal):
    - pulls Google News RSS per entity
    - writes normalized_news_documents
    - updates entity_daily_metrics.coverage_volume from dedup clusters

    External calls: YES (RSS). Gated by ENABLE_FETCH_MACRO_NEWS.
    """
    t0 = time.perf_counter()
    picked = 0
    fetched = 0
    normalized_written = 0
    raw_written = 0
    coverage_days_updated = 0

    with SessionLocal() as db:
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_FETCH_MACRO_NEWS):
            logger.info("job=refresh_normalized_entity_news disabled_by_runtime_flag=1")
            _rtlog(
                db,
                category="job",
                job_name="refresh_normalized_entity_news",
                provider="google_news_rss",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"disabled_by_runtime_flag": True, "picked": 0, "normalized_written": 0, "elapsed_ms": 0}

        entities = pick_entity_candidates(db, limit=int(max_entities))
        picked = len(entities)
        for e in entities:
            try:
                out = upsert_normalized_news_for_entity(db, entity=e, lookback_days=2, limit=80)
                fetched += int(out.get("fetched") or 0)
                normalized_written += int(out.get("normalized_written") or 0)
                raw_written += int(out.get("raw_written") or 0)
                coverage_days_updated += int(out.get("coverage_days_updated") or 0)
                db.commit()
            except Exception:
                db.rollback()
                logger.warning("refresh_normalized_entity_news failed entity=%s", getattr(e, "id", None), exc_info=True)
                continue

        dt = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "job=refresh_normalized_entity_news provider=google_news_rss picked=%s fetched=%s normalized_written=%s raw_written=%s coverage_days_updated=%s elapsed_ms=%s",
            picked,
            fetched,
            normalized_written,
            raw_written,
            coverage_days_updated,
            dt,
        )
        _rtlog(
            db,
            category="job",
            job_name="refresh_normalized_entity_news",
            provider="google_news_rss",
            status="success",
            message=f"picked={picked} fetched={fetched} normalized_written={normalized_written} coverage_days_updated={coverage_days_updated}",
            request_count=picked,
        )
        return {
            "picked": picked,
            "fetched": fetched,
            "normalized_written": normalized_written,
            "raw_written": raw_written,
            "coverage_days_updated": coverage_days_updated,
            "elapsed_ms": dt,
        }


@celery_app.task(name="app.worker.tasks.compute_entity_sentiment_series")
def compute_entity_sentiment_series(entity_id: str, period: str = "3M") -> dict:
    """
    Background compute for AI sentiment series buckets.
    Non-blocking API can enqueue this to fill missing buckets.
    """
    from app.services.entity_sentiment_series_ai import compute_sentiment_series_delta
    from app.services.runtime_flags import RuntimeFlagKey, ai_feature_enabled

    with SessionLocal() as db:
        # Admin-only feature: still respect AI runtime flags to prevent unintended spend.
        if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_NEWS_SUMMARY):
            _rtlog(
                db,
                category="ai",
                job_name="compute_entity_sentiment_series",
                provider="llm",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
            )
            return {"disabled_by_runtime_flag": True}
        try:
            eid = uuid.UUID(str(entity_id))
        except Exception:
            return {"error": "invalid_entity_id"}

        pts, err, meta = compute_sentiment_series_delta(db, entity_id=eid, period=period)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        _rtlog(
            db,
            category="ai",
            job_name="compute_entity_sentiment_series",
            provider="llm",
            status="success" if err is None else "failed",
            message=f"period={period} computed={meta.get('computed')} reused={meta.get('reused')} llm_calls={meta.get('llm_calls')} err={err}",
            no_provider_call=False,
            request_count=int(meta.get("llm_calls") or 0),
        )
        return {"points": len(pts), "err": err, "meta": meta}

@celery_app.task(name="app.worker.tasks.retention_cleanup_v1")
def retention_cleanup_v1() -> dict:
    """
    Daily retention & cleanup (policy V1). Safe to re-run; see app.services.retention_cleanup.
    """
    from app.db.session import engine
    from app.db.schema_patch import run_schema_patches
    from app.services.retention_cleanup import run_retention_cleanup_v1 as apply_retention_v1

    run_schema_patches(engine)
    with SessionLocal() as db:
        try:
            out = apply_retention_v1(db)
            db.commit()
            return out
        except Exception:
            logger.exception("retention_cleanup_v1 failed")
            db.rollback()
            raise


@celery_app.task(name="app.worker.tasks.refresh_triple_signal_metrics")
def refresh_triple_signal_metrics() -> dict:
    """
    Refresh normalized trading/news/search triple signal metrics from local DB only.
    """
    t0 = time.perf_counter()
    entity_count = 0
    row_count = 0
    with SessionLocal() as db:
        entity_ids = db.scalars(
            select(PortfolioEntity.id).where(PortfolioEntity.instrument_id.isnot(None))
        ).all()
        for eid in entity_ids:
            try:
                n = upsert_entity_triple_signal_metrics(db, eid)
            except Exception:
                logger.warning("refresh_triple_signal_metrics failed entity=%s", eid, exc_info=True)
                continue
            if n > 0:
                entity_count += 1
                row_count += n
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=refresh_triple_signal_metrics provider=local_db request_count=0 fallback_count=0 symbol_count=%s elapsed_ms=%s rows=%s",
        entity_count,
        dt,
        row_count,
    )
    return {"entities": entity_count, "rows": row_count, "elapsed_ms": dt}


@celery_app.task(name="app.worker.tasks.massive_analysis_light_job")
def massive_analysis_light_job(max_entities: int = _MASSIVE_LIGHT_ENTITY_LIMIT) -> dict:
    """
    Massive isolated analysis pass (does not write price tables and is not exposed to UI/API payloads).
    """
    t0 = time.perf_counter()
    processed = 0
    skipped = 0
    no_news = 0
    anomaly_count = 0
    with SessionLocal() as db:
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_MASSIVE_ANALYSIS):
            dt = round((time.perf_counter() - t0) * 1000, 2)
            logger.info("job=massive_analysis_light_job disabled_by_runtime_flag=1 elapsed_ms=%s", dt)
            _rtlog(
                db,
                category="job",
                job_name="massive_analysis_light_job",
                provider="massive_local",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"processed": 0, "skipped": 0, "disabled_by_runtime_flag": True, "elapsed_ms": dt}
        candidates = select_light_entity_candidates(db, limit=max_entities)
        for eid in candidates:
            try:
                ok = run_massive_light_analysis_for_entity(db, eid)
                if ok:
                    processed += 1
            except Exception:
                logger.warning("massive_analysis_light_job failed entity=%s", eid, exc_info=True)
                skipped += 1
        db.commit()
    dt = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "job=massive_analysis_light_job provider=massive_local request_count=0 fallback_count=0 "
        "processed_entities=%s skipped_entities=%s no_news_entities=%s anomaly_count=%s elapsed_ms=%s",
        processed,
        skipped,
        no_news,
        anomaly_count,
        dt,
    )
    with SessionLocal() as db:
        _rtlog(
            db,
            category="job",
            job_name="massive_analysis_light_job",
            provider="massive_local",
            status="success",
            message=f"processed={processed} skipped={skipped} anomaly_count={anomaly_count}",
            no_provider_call=True,
            request_count=0,
            fallback_count=0,
        )
    return {
        "processed": processed,
        "skipped": skipped,
        "no_news": no_news,
        "anomaly_count": anomaly_count,
        "elapsed_ms": dt,
        "limit": max_entities,
    }


@celery_app.task(name="app.worker.tasks.massive_backfill_loop")
def massive_backfill_loop(batch_size: int = MASSIVE_BACKFILL_BATCH_SIZE) -> dict:
    """
    Queue inspection only: does **not** call Massive (repair scan is the sole Massive consumer).
    Pending rows stay pending for optional future non-Massive processing.
    """
    t0 = time.perf_counter()
    if massive_paused():
        dt = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "job=massive_backfill_loop provider=massive_backfill skipped_due_to_pause=1 massive_request_count_per_run=0 picked=0 processed=0 wrote_quotes=0 wrote_ohlcv=0 requeued=0 elapsed_ms=%s",
            dt,
        )
        with SessionLocal() as db:
            _rtlog(
                db,
                level="warning",
                category="provider",
                job_name="massive_backfill_loop",
                provider="massive_backfill",
                status="paused",
                message="skipped_due_to_pause",
                no_provider_call=True,
                request_count=0,
            )
        return {"picked": 0, "processed": 0, "skipped_due_to_pause": True, "elapsed_ms": dt}

    with SessionLocal() as db:
        if not provider_enabled(db, RuntimeFlagKey.ENABLE_MASSIVE_BACKFILL):
            dt = round((time.perf_counter() - t0) * 1000, 2)
            logger.info(
                "job=massive_backfill_loop provider=massive_backfill disabled_by_runtime_flag=1 "
                "skipped_due_to_flag=1 picked=0 processed=0 elapsed_ms=%s",
                dt,
            )
            _rtlog(
                db,
                category="provider",
                job_name="massive_backfill_loop",
                provider="massive_backfill",
                status="skipped",
                message="disabled_by_runtime_flag",
                disabled_by_runtime_flag=True,
                no_provider_call=True,
                request_count=0,
            )
            return {"picked": 0, "processed": 0, "disabled_by_runtime_flag": True, "elapsed_ms": dt}
        rows = pick_pending_backfill_rows(db, limit=int(batch_size))
        if not rows:
            dt = round((time.perf_counter() - t0) * 1000, 2)
            return {"picked": 0, "processed": 0, "elapsed_ms": dt}

        dt = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "job=massive_backfill_loop skipped_massive_api=1 repair_scan_exclusive=1 picked=%s "
            "rows_remain_pending=1 message=massive_backfill_does_not_call_massive elapsed_ms=%s",
            len(rows),
            dt,
        )
        _rtlog(
            db,
            category="provider",
            job_name="massive_backfill_loop",
            provider="massive_backfill",
            status="skipped",
            message="massive_backfill_massive_api_disabled_repair_scan_exclusive",
            no_provider_call=True,
            request_count=0,
            symbol_count=len(rows),
        )
        return {
            "picked": len(rows),
            "processed": 0,
            "skipped_massive_api_repair_scan_exclusive": True,
            "elapsed_ms": dt,
        }


@celery_app.task(name="app.worker.tasks.massive_market_repair_scan")
def massive_market_repair_scan() -> dict:
    """
    Rolling repair for tracked symbols only (DB-first). Single-flight Redis lock; off-hours 60m cooldown
    enforced again after lock (not beat-only).
    """
    from datetime import datetime, timezone

    allow, throttle_reason = repair_scan_should_execute_tick(now_utc=datetime.now(timezone.utc))
    if not allow:
        logger.info("job=massive_repair_scan_tick skipped=1 reason=%s", throttle_reason)
        return {"skipped": True, "reason": throttle_reason}

    if massive_paused():
        logger.info("job=massive_repair_scan_tick skipped=1 reason=massive_paused")
        return {"skipped": True, "reason": "massive_paused"}

    acquired, lock_token = acquire_massive_repair_scan_lock()
    if not acquired:
        logger.info("job=massive_repair_scan_tick skipped=1 reason=concurrent_repair_scan_lock_held")
        return {"skipped": True, "reason": "concurrent_repair_scan_lock_held"}

    try:
        cooldown_block = repair_scan_offhours_cooldown_blocks_after_lock()
        if cooldown_block:
            logger.info("job=massive_repair_scan_tick skipped=1 reason=%s", cooldown_block)
            return {"skipped": True, "reason": cooldown_block}

        with SessionLocal() as db:
            if not provider_enabled(db, RuntimeFlagKey.ENABLE_MASSIVE_BACKFILL):
                logger.info("job=massive_repair_scan_tick skipped=1 reason=disabled_by_runtime_flag")
                return {"skipped": True, "reason": "disabled_by_runtime_flag"}
            return run_massive_market_repair_scan(db)
    finally:
        release_massive_repair_scan_lock(lock_token)

