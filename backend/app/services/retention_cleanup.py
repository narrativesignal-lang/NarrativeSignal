"""
Retention & cleanup policy V1 (additive, idempotent deletes).

See module docstring on RETENTION_RULES for table mapping. Adjust ages here in one place
for future policy revisions (V2, env overrides, etc.).

NEVER delete from this module:
  users, credit_ledger, reports, monitoring_schedules, portfolios / entities / terms,
  keyword_groups / terms / rss_feeds / entity_configs, research_* (folders, projects,
  setup snapshots), instruments (reference), user_data_subscriptions, community tables,
  index_points (normalized group time-series buckets), spike_events (unless a future
  policy explicitly adds them).

Safe to re-run: all deletes are WHERE-created-before cutoff; second run removes 0 rows.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.models.data_subscription import EntityDailyMetric, MarketQuoteSnapshot, NormalizedNewsDocument, OhlcvSnapshot
from app.models.document import SourceDocument
from app.models.document_analysis import DocumentAnalysis
from app.models.group_document import GroupDocument
from app.models.macro_event import MacroEvent
from app.models.monitoring import MonitoringRun, TriggeredAlert

logger = logging.getLogger(__name__)

# --- Policy ages (days). Tune only here. ---------------------------------
DAYS_ENTITY_DAILY_METRICS = 60
DAYS_NEWS_METADATA_AND_RUNS = 30
DAYS_MARKET_SNAPSHOT_CACHE = 14
DAYS_SOURCE_DOCUMENTS_RAW = 7

"""
Retention V1 mapping (implementation vs product spec):

  ~60d  entity_daily_metrics           by metric_date (daily grain, not created_at)
  ~30d  normalized_news_documents    created_at (ingested normalized metadata)
  ~30d  macro_events                   timestamp (event time)
  ~30d  monitoring_runs                created.at (schedule run logs)
  ~30d  triggered_alerts              created_at (ephemeral alert feed; not saved reports)

  ~14d  market_quote_snapshots         last_attempt_at / last_success_at (quote cache)
  ~14d  ohlcv_snapshots                last_attempt_at / last_success_at (OHLCV cache)

  ~7d   source_documents               created_at (raw ingested article body / RSS rows)
        + document_analyses, group_documents for deleted docs (FK cleanup first)

  NOT in DB / deferred explicitly:
  - API request logs (no table yet)
  - debug file logs (not in Postgres)
  - Celery failure stacks (broker/backend; not migrated here)
  - research cache / raw LLM payloads (no dedicated TTL table; Report.payload retained)
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_retention_cleanup_v1(db: Session) -> dict[str, Any]:
    """
    Apply V1 retention deletes. Returns per-step deleted rowcounts for logs/metrics.
    """
    now = _utcnow()
    today = now.date()
    stats: dict[str, int] = {}

    # ------------------------------------------------------------------ 60d: entity daily metrics
    cutoff_metric_date = today - timedelta(days=DAYS_ENTITY_DAILY_METRICS)
    r = db.execute(
        delete(EntityDailyMetric).where(EntityDailyMetric.metric_date < cutoff_metric_date)
    )
    stats["entity_daily_metrics"] = r.rowcount or 0

    # ------------------------------------------------------------------ 30d: normalized news metadata
    cutoff30 = now - timedelta(days=DAYS_NEWS_METADATA_AND_RUNS)
    r = db.execute(delete(NormalizedNewsDocument).where(NormalizedNewsDocument.created_at < cutoff30))
    stats["normalized_news_documents"] = r.rowcount or 0

    r = db.execute(delete(MacroEvent).where(MacroEvent.timestamp < cutoff30))
    stats["macro_events"] = r.rowcount or 0

    r = db.execute(delete(MonitoringRun).where(MonitoringRun.created_at < cutoff30))
    stats["monitoring_runs"] = r.rowcount or 0

    r = db.execute(delete(TriggeredAlert).where(TriggeredAlert.created_at < cutoff30))
    stats["triggered_alerts"] = r.rowcount or 0

    # ------------------------------------------------------------------ 14d: market / OHLCV caches
    cutoff14 = now - timedelta(days=DAYS_MARKET_SNAPSHOT_CACHE)
    stale_quote = or_(
        and_(MarketQuoteSnapshot.last_attempt_at.isnot(None), MarketQuoteSnapshot.last_attempt_at < cutoff14),
        and_(
            MarketQuoteSnapshot.last_attempt_at.is_(None),
            MarketQuoteSnapshot.last_success_at.isnot(None),
            MarketQuoteSnapshot.last_success_at < cutoff14,
        ),
    )
    r = db.execute(delete(MarketQuoteSnapshot).where(stale_quote))
    stats["market_quote_snapshots"] = r.rowcount or 0

    stale_ohlcv = or_(
        and_(OhlcvSnapshot.last_attempt_at.isnot(None), OhlcvSnapshot.last_attempt_at < cutoff14),
        and_(
            OhlcvSnapshot.last_attempt_at.is_(None),
            OhlcvSnapshot.last_success_at.isnot(None),
            OhlcvSnapshot.last_success_at < cutoff14,
        ),
    )
    r = db.execute(delete(OhlcvSnapshot).where(stale_ohlcv))
    stats["ohlcv_snapshots"] = r.rowcount or 0

    # ------------------------------------------------------------------ 7d: raw source documents + dependents
    cutoff7 = now - timedelta(days=DAYS_SOURCE_DOCUMENTS_RAW)
    old_doc_ids = select(SourceDocument.id).where(SourceDocument.created_at < cutoff7)
    r = db.execute(delete(DocumentAnalysis).where(DocumentAnalysis.document_id.in_(old_doc_ids)))
    stats["document_analyses"] = r.rowcount or 0
    r = db.execute(delete(GroupDocument).where(GroupDocument.document_id.in_(old_doc_ids)))
    stats["group_documents"] = r.rowcount or 0
    r = db.execute(delete(SourceDocument).where(SourceDocument.created_at < cutoff7))
    stats["source_documents"] = r.rowcount or 0

    total = sum(stats.values())
    logger.info(
        "retention_v1_complete total_deleted=%s breakdown=%s",
        total,
        stats,
    )
    return {"ok": True, "cutoffs_utc": {"now": now.isoformat(), "metric_date_before": str(cutoff_metric_date)}, "deleted": stats}
