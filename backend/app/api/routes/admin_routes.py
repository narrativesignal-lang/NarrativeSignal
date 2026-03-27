"""Admin-only routes: user management, etc."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin, user_is_admin
from app.db.session import get_db
from app.models.user import User


router = APIRouter(dependencies=[])


class AdminUserPatchBody(BaseModel):
    paid_access: bool | None = None


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[dict]:
    """List all users (admin only). Includes username, role, created_at, session/plan info."""
    rows = db.execute(
        select(User).order_by(User.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": str(u.id),
            "username": getattr(u, "username", u.email),
            "email": u.email,
            "is_admin": user_is_admin(u),
            "paid_access": getattr(u, "paid_access", False),
            "credits_balance": u.credits_balance,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "token_version": getattr(u, "token_version", 0),
        }
        for u in rows
    ]


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    payload: AdminUserPatchBody,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Toggle paid features (e.g. event timeline unlock with credits)."""
    if payload.paid_access is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.paid_access = bool(payload.paid_access)
    db.commit()
    db.refresh(u)
    return {
        "id": str(u.id),
        "username": getattr(u, "username", u.email),
        "paid_access": u.paid_access,
        "credits_balance": u.credits_balance,
    }


@router.get("/diag/core-data")
def admin_core_data_diag(
    _admin: User = Depends(require_admin),
) -> dict:
    """Redis-backed counters: snapshot hits, fallbacks, warmup, slow routes."""
    from app.services.core_data_diag import get_core_diag_snapshot

    return get_core_diag_snapshot()


@router.post("/market/refresh-cache")
def admin_refresh_market_cache(
    _admin: User = Depends(require_admin),
) -> dict:
    """
    Enqueue Celery jobs to refresh V1 core shared market quotes + full OHLCV snapshots.
    Admin/dev only; does not run Yahoo inline.
    """
    try:
        from app.worker.tasks import refresh_core_market_cache_admin

        job = refresh_core_market_cache_admin.delay()
        return {
            "enqueued": True,
            "task": "refresh_core_market_cache_admin",
            "task_id": job.id,
            "scope": "CORE_SHARED_MARKET_SYMBOLS_V1 (quotes + all OHLCV periods)",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not enqueue market cache refresh (is Celery broker up?): {exc}",
        ) from exc
