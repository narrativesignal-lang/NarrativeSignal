"""Background warmup for core first-screen data (non-blocking for ASGI startup)."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


def _run_warmup_sync() -> bool:
    """Market snapshots + macro news DB snapshots (+ best-effort Celery entity metrics)."""
    t0 = time.perf_counter()
    try:
        from app.db.session import SessionLocal
        from app.services.market_snapshots import (
            collect_symbols_for_scheduled_market_refresh,
            upsert_ohlcv_from_fetch,
            upsert_quote_from_fetch,
        )
        from app.services.macro_news_snapshot import rebuild_snapshots_all_categories

        lite_periods: tuple[str, ...] = ("1D", "1M")

        with SessionLocal() as db:
            syms = sorted(collect_symbols_for_scheduled_market_refresh(db))
            for sym in syms:
                try:
                    upsert_quote_from_fetch(db, sym)
                except Exception:
                    logger.warning("core_data_warmup quote failed %s", sym, exc_info=True)
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("core_data_warmup quote batch commit failed")

        with SessionLocal() as db:
            for sym in syms:
                for period in lite_periods:
                    try:
                        upsert_ohlcv_from_fetch(db, sym, period)
                    except Exception:
                        logger.warning(
                            "core_data_warmup ohlcv failed %s %s", sym, period, exc_info=True
                        )
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("core_data_warmup ohlcv batch commit failed")

        with SessionLocal() as db:
            try:
                rebuild_snapshots_all_categories(db)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("core_data_warmup macro news snapshot rebuild failed")

        try:
            from app.worker.tasks import sync_entity_daily_metrics

            sync_entity_daily_metrics.apply_async(countdown=8)
            logger.info("core_data_warmup scheduled sync_entity_daily_metrics (celery)")
        except Exception:
            logger.info("core_data_warmup: celery entity sync not scheduled (broker offline?)")

        dt = time.perf_counter() - t0
        logger.info("core_data_warmup finished duration_s=%.2f symbols=%d", dt, len(syms))
        return True
    except Exception:
        logger.exception("core_data_warmup FAIL duration_s=%.2f", time.perf_counter() - t0)
        return False


def start_core_data_warmup_background() -> None:
    """Fire-and-forget daemon thread; never blocks process bind."""

    def _target() -> None:
        from app.services.core_data_diag import record_warmup

        logger.info("core_data_warmup START (background thread)")
        ok = _run_warmup_sync()
        record_warmup(ok)

    t = threading.Thread(target=_target, name="core-data-warmup", daemon=True)
    t.start()
    logger.info("core_data_warmup thread spawned")
