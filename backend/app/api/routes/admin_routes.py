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
