from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from app.core.config import settings


celery_app = Celery(
    "narrative_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_default_queue="default",
    timezone="America/New_York",
    enable_utc=False,
    beat_schedule={
        "tick-schedules-every-minute": {
            "task": "app.worker.tasks.tick_schedules",
            "schedule": crontab(minute="*/1"),
        },
        "daily-info-report-0705-ny": {
            "task": "app.worker.tasks.generate_daily_reports",
            "schedule": crontab(minute="5", hour="7"),
        },
        "fetch-macro-news-every-15-min": {
            "task": "app.worker.tasks.fetch_macro_news",
            "schedule": crontab(minute="*/15"),
        },
        # Google News list for Macro tab (DB snapshot); light interval for dev.
        "refresh-macro-news-list-snapshots-12m": {
            "task": "app.worker.tasks.refresh_macro_news_list_snapshots",
            "schedule": crontab(minute="2,14,26,38,50"),
        },
        "refresh-market-quotes-every-15-min": {
            "task": "app.worker.tasks.refresh_market_quotes",
            "schedule": crontab(minute="*/15"),
        },
        # Twelve fixed warm pool: Redis + DB snapshots for validated symbols only (conservative credits).
        "warm-pool-twelve-quotes-15m": {
            "task": "app.worker.tasks.warm_pool_twelve_quotes",
            "schedule": crontab(minute="*/15"),
        },
        "warm-pool-twelve-time-series-1m-hourly": {
            "task": "app.worker.tasks.warm_pool_twelve_time_series_1m",
            "schedule": crontab(minute="5"),
        },
        # Twelve dynamic active pool (global): separate from fixed warm pool list + schedules.
        "active-pool-twelve-quotes-30m": {
            "task": "app.worker.tasks.refresh_active_pool_twelve_quotes",
            "schedule": crontab(minute="8,38"),
        },
        "active-pool-twelve-time-series-1m-2h": {
            "task": "app.worker.tasks.refresh_active_pool_twelve_time_series_1m",
            "schedule": crontab(minute="22", hour="*/2"),
        },
        # OHLCV: shared snapshots for the same symbol universe (less frequent than quotes).
        "refresh-market-ohlcv-every-6-hours": {
            "task": "app.worker.tasks.refresh_market_ohlcv_snapshots",
            "schedule": crontab(minute="25", hour="*/6"),
        },
        "sync-entity-daily-metrics-daily-0210-ny": {
            "task": "app.worker.tasks.sync_entity_daily_metrics",
            "schedule": crontab(minute="10", hour="2"),
        },
        # Retention / ephemeral data (see app.services.retention_cleanup RETENTION_RULES)
        "retention-cleanup-v1-daily-0430-ny": {
            "task": "app.worker.tasks.retention_cleanup_v1",
            "schedule": crontab(minute="30", hour="4"),
        },
    },
)


@worker_process_init.connect
def _run_schema_patches_on_worker_start(**_kwargs: object) -> None:
    """Additive patches once per worker process (API runs the same via init_db on startup)."""
    from app.db.schema_patch import run_schema_patches
    from app.db.session import engine

    run_schema_patches(engine)

