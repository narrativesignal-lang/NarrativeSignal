from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.models.system_runtime_log import SystemRuntimeLog

logger = logging.getLogger(__name__)

# Keep storage tiny on purpose.
_HARD_CAP_ROWS = 250
_DEFAULT_LIMIT = 50


def append_runtime_log(
    db: Session,
    *,
    level: str = "info",
    category: str = "system",
    job_name: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    message: str,
    disabled_by_runtime_flag: bool = False,
    no_provider_call: bool = False,
    request_count: int | None = None,
    fallback_count: int | None = None,
    symbol_count: int | None = None,
    commit: bool = True,
) -> None:
    """
    Append a small, user-visible runtime log row.
    Best-effort: errors should never break jobs/routes.
    """
    try:
        row = SystemRuntimeLog(
            created_at=datetime.now(timezone.utc),
            level=(level or "info").lower()[:16],
            category=(category or "system").lower()[:24],
            job_name=(job_name[:80] if job_name else None),
            provider=(provider[:40] if provider else None),
            status=(status[:16] if status else None),
            message=(message or "")[:2000],
            disabled_by_runtime_flag=bool(disabled_by_runtime_flag),
            no_provider_call=bool(no_provider_call),
            request_count=request_count,
            fallback_count=fallback_count,
            symbol_count=symbol_count,
        )
        db.add(row)
        db.flush()

        # Trim old rows (tiny bounded table).
        total = db.scalar(select(SystemRuntimeLog.id).order_by(desc(SystemRuntimeLog.id)).offset(_HARD_CAP_ROWS).limit(1))
        if total is not None:
            cutoff_id = int(total)
            db.execute(delete(SystemRuntimeLog).where(SystemRuntimeLog.id <= cutoff_id))
        if commit:
            db.commit()
    except Exception:
        try:
            if commit:
                db.rollback()
        except Exception:
            pass
        logger.debug("append_runtime_log failed (ignored)", exc_info=True)


def list_recent_runtime_logs(
    db: Session,
    *,
    limit: int = _DEFAULT_LIMIT,
    category: str | None = None,
    min_level: str | None = None,
) -> list[SystemRuntimeLog]:
    n = int(limit or _DEFAULT_LIMIT)
    n = max(1, min(n, 200))
    stmt = select(SystemRuntimeLog).order_by(desc(SystemRuntimeLog.created_at)).limit(n)

    if category and category.lower() != "all":
        stmt = stmt.where(SystemRuntimeLog.category == category.lower())

    if min_level:
        # simple threshold: warning/error
        low = min_level.lower().strip()
        if low in {"warning", "warn"}:
            stmt = stmt.where(SystemRuntimeLog.level.in_(["warning", "error"]))
        elif low == "error":
            stmt = stmt.where(SystemRuntimeLog.level == "error")

    return list(db.execute(stmt).scalars().all())

