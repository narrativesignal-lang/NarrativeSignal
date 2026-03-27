from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import feedparser
from croniter import croniter

from app.core.platform_tz import now_platform
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.index_point import IndexPoint
from app.models.keyword_group import KeywordGroup
from app.models.macro_event import MacroEvent
from app.models.monitoring import MonitoringRun, MonitoringSchedule
from app.models.portfolio import PortfolioEntity
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
from app.services.market_snapshots import (
    OHLCV_CACHE_PERIODS,
    collect_symbols_for_scheduled_market_refresh,
    upsert_ohlcv_from_fetch,
    upsert_quote_from_fetch,
)
from app.worker.celery_app import celery_app
from app.models.data_subscription import UserDataSubscription
from app.services.subscriptions import ensure_subscription

logger = logging.getLogger(__name__)


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
        for sym in syms:
            try:
                upsert_quote_from_fetch(db, sym)
                q_ok += 1
            except Exception:
                logger.warning("quote upsert failed in batch for %s", sym, exc_info=True)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("_refresh_market_snapshots_sync quote commit failed")
    cells = 0
    with SessionLocal() as db:
        for sym in syms:
            for period in periods:
                try:
                    upsert_ohlcv_from_fetch(db, sym, period)
                    cells += 1
                except Exception:
                    logger.warning("ohlcv upsert failed %s period=%s", sym, period, exc_info=True)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("_refresh_market_snapshots_sync ohlcv commit failed")
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
                analyzed += analyze_documents(db=db, group_id=gid, document_ids=newly_linked)

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
        counts = rebuild_snapshots_all_categories(db)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh_macro_news_list_snapshots commit failed")
            raise
    return {"snapshot_counts": counts}


@celery_app.task(name="app.worker.tasks.fetch_macro_news")
def fetch_macro_news() -> dict:
    """
    Ingest macro news from RSS feeds into macro_events.
    Runs every 15 minutes via beat. Deduplicates by title.
    """
    inserted = 0
    with SessionLocal() as db:
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
    return {"inserted": inserted}


@celery_app.task(name="app.worker.tasks.refresh_market_quotes")
def refresh_market_quotes() -> dict:
    """
    Refresh shared market_quote_snapshots: V1 core + default indices + market_quote subscriptions.
    GET /market/* reads snapshots only; failures keep prior cached values inside upsert.
    """
    with SessionLocal() as db:
        syms = collect_symbols_for_scheduled_market_refresh(db)
        for sym in sorted(syms):
            try:
                upsert_quote_from_fetch(db, sym)
            except Exception:
                logger.warning("refresh_market_quotes failed for %s", sym, exc_info=True)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh_market_quotes commit failed")
    return {"symbols_refreshed": len(syms)}


@celery_app.task(name="app.worker.tasks.refresh_market_ohlcv_snapshots")
def refresh_market_ohlcv_snapshots() -> dict:
    """Periodic OHLCV snapshot fill (low frequency). Request handlers do not call providers."""
    cells = 0
    failures = 0
    with SessionLocal() as db:
        syms = collect_symbols_for_scheduled_market_refresh(db)
        for sym in sorted(syms):
            for period in OHLCV_CACHE_PERIODS:
                try:
                    upsert_ohlcv_from_fetch(db, sym, period)
                    cells += 1
                except Exception:
                    failures += 1
                    logger.warning("refresh_market_ohlcv_snapshots failed %s period=%s", sym, period, exc_info=True)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh_market_ohlcv_snapshots commit failed")
    return {"cells_upserted": cells, "failures": failures}


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
    import time

    from app.services.market_indices_config import CORE_SHARED_MARKET_SYMBOLS_V1

    syms = sorted(CORE_SHARED_MARKET_SYMBOLS_V1)
    with SessionLocal() as db:
        for i, sym in enumerate(syms):
            try:
                upsert_quote_from_fetch(db, sym)
            except Exception:
                logger.warning("warmup quote failed %s", sym, exc_info=True)
            if i + 1 < len(syms):
                time.sleep(0.2)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("warmup_core_market_snapshots quote commit failed")

    lite_periods: tuple[str, ...] = ("1D", "1M")
    with SessionLocal() as db:
        for i, sym in enumerate(syms):
            for period in lite_periods:
                try:
                    upsert_ohlcv_from_fetch(db, sym, period)
                except Exception:
                    logger.warning("warmup ohlcv failed %s %s", sym, period, exc_info=True)
            if i + 1 < len(syms):
                time.sleep(0.3)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("warmup_core_market_snapshots ohlcv commit failed")
    return {"warmup": "core", "symbols": len(syms), "ohlcv_periods": list(lite_periods)}


@celery_app.task(name="app.worker.tasks.sync_entity_daily_metrics")
def sync_entity_daily_metrics() -> dict:
    """Daily job: Google Trends → entity_daily_metrics.search_trend (pytrends)."""
    total_rows = 0
    n_entities = 0
    invalid_subscriptions = 0
    orphan_subscriptions = 0
    repaired_subscriptions = 0
    with SessionLocal() as db:
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
    return {
        "entities": n_entities,
        "metric_rows": total_rows,
        "invalid_subscriptions_removed": invalid_subscriptions,
        "orphan_subscriptions_removed": orphan_subscriptions,
        "subscriptions_repaired": repaired_subscriptions,
    }


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

