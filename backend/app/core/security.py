from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext
from passlib.exc import MissingBackendError, UnknownHashError

from app.core.config import settings


# PBKDF2 is the default for new hashes (broad compatibility). Bcrypt remains as a
# secondary scheme so legacy password rows still verify when the bcrypt backend is installed.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash or not isinstance(password_hash, str):
        return False
    try:
        return bool(pwd_context.verify(password, password_hash))
    except (UnknownHashError, MissingBackendError, ValueError, TypeError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, subject: str, user_id: str, token_version: int = 0) -> str:
    exp = _now() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": subject,
        "uid": user_id,
        "ver": token_version,
        "typ": "access",
        "exp": exp,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(*, subject: str, user_id: str, token_version: int = 0) -> str:
    exp = _now() + timedelta(days=settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": subject,
        "uid": user_id,
        "ver": token_version,
        "typ": "refresh",
        "exp": exp,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer=settings.jwt_issuer)

