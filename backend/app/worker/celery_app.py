from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

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
        "refresh-market-quotes-every-15-min": {
            "task": "app.worker.tasks.refresh_market_quotes",
            "schedule": crontab(minute="*/15"),
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

