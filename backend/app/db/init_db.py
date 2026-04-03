"""
Idempotent database initialization on application startup.

- Ensures all ORM models are registered on Base.metadata
- Creates missing tables (create_all is safe for existing DBs)
- Applies additive schema patches for legacy databases
"""

from __future__ import annotations

import logging
import time

from app.db.base import Base
from app.db.schema_patch import run_schema_patches
from app.db.session import engine

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Load models, create any missing tables, run safe schema patches."""
    import app.models  # noqa: F401 — register all models with SQLAlchemy metadata
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    # Startup race protection: Postgres DNS/service may not be ready when the API container starts.
    # Retry up to ~30s before failing the process.
    deadline = time.monotonic() + 30.0
    attempt = 0
    last_err: Exception | None = None
    while True:
        attempt += 1
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            break
        except OperationalError as e:
            last_err = e
            if time.monotonic() >= deadline:
                break
            logger.warning(
                "DB not ready yet (init_db). attempt=%s retrying_in_sec=%s err=%s",
                attempt,
                2,
                str(e).splitlines()[0][:240],
            )
            time.sleep(2.0)
        except Exception as e:
            last_err = e
            if time.monotonic() >= deadline:
                break
            logger.warning(
                "DB init probe failed (init_db). attempt=%s retrying_in_sec=%s err=%s",
                attempt,
                2,
                str(e).splitlines()[0][:240],
            )
            time.sleep(2.0)

    if last_err is not None and time.monotonic() >= deadline:
        raise RuntimeError(f"Database not reachable after retries: {last_err}") from last_err

    Base.metadata.create_all(bind=engine)
    run_schema_patches(engine)
    logger.info("Database init complete (create_all + schema patches).")
