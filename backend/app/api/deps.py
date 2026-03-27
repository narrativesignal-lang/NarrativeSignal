from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        uid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Single-session: reject if token version doesn't match (session invalidated by new login)
    token_ver = payload.get("ver", 0)
    user_ver = getattr(user, "token_version", 0)
    if token_ver != user_ver:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired because your account was signed in somewhere else.",
        )
    return user


def get_current_user_optional(
    db: Session = Depends(get_db), token: str | None = Depends(oauth2_scheme_optional)
) -> User | None:
    """Returns current user if valid token present, else None. Does not raise."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            return None
        user_id = payload.get("uid")
        if not user_id:
            return None
        uid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        return None
    user = db.get(User, uid)
    if not user:
        return None
    token_ver = payload.get("ver", 0)
    if token_ver != getattr(user, "token_version", 0):
        return None
    return user


def _admin_allowlist_sets() -> tuple[set[str], set[str]]:
    names = {x.strip().lower() for x in (settings.admin_usernames or "").split(",") if x.strip()}
    emails = {x.strip().lower() for x in (settings.admin_emails or "").split(",") if x.strip()}
    return names, emails


def user_is_admin(user: User) -> bool:
    """
    Admin flag for admin-only HTTP APIs and /auth/me.is_admin.
    Uses users.is_admin; optional ADMIN_USERNAMES / ADMIN_EMAILS env narrows who counts as admin.
    """
    if not getattr(user, "is_admin", False):
        return False
    name_set, email_set = _admin_allowlist_sets()
    if not name_set and not email_set:
        return True
    uname = (getattr(user, "username", None) or "").strip().lower()
    email = (getattr(user, "email", None) or "").strip().lower()
    if name_set and email_set:
        return uname in name_set or email in email_set
    if name_set:
        return uname in name_set
    return email in email_set


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not user_is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

