"""
Idempotent database initialization on application startup.

- Ensures all ORM models are registered on Base.metadata
- Creates missing tables (create_all is safe for existing DBs)
- Applies additive schema patches for legacy databases
"""

from __future__ import annotations

import logging

from app.db.base import Base
from app.db.schema_patch import run_schema_patches
from app.db.session import engine

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Load models, create any missing tables, run safe schema patches."""
    import app.models  # noqa: F401 — register all models with SQLAlchemy metadata

    Base.metadata.create_all(bind=engine)
    run_schema_patches(engine)
    logger.info("Database init complete (create_all + schema patches).")
