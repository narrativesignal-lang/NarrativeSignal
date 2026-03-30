from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.ai_access import AI_FEATURES_FORBIDDEN_DETAIL
from app.core.config import settings
from app.core.feature_access import FeatureKey, can_access_feature
from app.core.user_admin import user_is_admin
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


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not user_is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_feature(feature_name: str):
    """Dependency factory: 403 with ``AI_FEATURES_FORBIDDEN_DETAIL`` if ``can_access_feature`` fails."""

    def _dep(current_user: User = Depends(get_current_user)) -> User:
        if not can_access_feature(current_user, feature_name):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AI_FEATURES_FORBIDDEN_DETAIL)
        return current_user

    return _dep


# Backward-compatible alias: HEAVY AI document-style entitlement (same 403 message).
require_paid_ai_access = require_feature(FeatureKey.DOCUMENT_LLM_ANALYSIS)

