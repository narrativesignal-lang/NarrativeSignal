from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.deps import get_current_user, user_is_admin
from app.core.plan_entitlements import AiAccessLevel, PlanCode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
)


router = APIRouter()
REFRESH_COOKIE_NAME = "narrative_refresh"


def _me_response(user: User) -> MeResponse:
    return MeResponse(
        id=str(user.id),
        username=getattr(user, "username", user.email),
        email=user.email,
        profile_name=(getattr(user, "profile_name", None) or "") or "",
        credits_balance=user.credits_balance,
        plan_code=(getattr(user, "plan_code", None) or PlanCode.FREE.value) or PlanCode.FREE.value,
        ai_access_level=(getattr(user, "ai_access_level", None) or AiAccessLevel.NONE.value)
        or AiAccessLevel.NONE.value,
        paid_access=getattr(user, "paid_access", False),
        is_admin=user_is_admin(user),
    )


@router.post("/register", response_model=MeResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> MeResponse:
    email_n = str(payload.email).strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email_n)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    username: str | None = None
    for _ in range(32):
        candidate = f"u_{uuid.uuid4().hex}"
        if db.scalar(select(User).where(User.username == candidate)):
            continue
        username = candidate
        break
    if not username:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not allocate account id")

    user = User(
        username=username,
        email=email_n,
        password_hash=hash_password(payload.password),
        credits_balance=10_000,
        token_version=0,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return _me_response(user)


def _resolve_user(db: Session, login: str) -> User | None:
    """Resolve login: reserved admin handle, then username, then email (legacy + email login)."""
    login = login.strip().lower()
    if not login:
        return None
    if login == "admin":
        return db.scalar(select(User).where(User.username == "admin"))
    by_username = db.scalar(select(User).where(func.lower(User.username) == login))
    if by_username:
        return by_username
    return db.scalar(select(User).where(func.lower(User.email) == login))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = _resolve_user(db, payload.email)
    if not user or not verify_password(payload.password.strip(), user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Single session: increment token_version to invalidate previous sessions
    prev_ver = int(getattr(user, "token_version", 0) or 0)
    user.token_version = prev_ver + 1
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("login: failed to persist token_version")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login temporarily unavailable. Please try again.",
        ) from None

    ver = int(getattr(user, "token_version", 0) or 0)

    try:
        access = create_access_token(subject=user.username, user_id=str(user.id), token_version=ver)
        refresh = create_refresh_token(subject=user.username, user_id=str(user.id), token_version=ver)
    except Exception:
        logger.exception("login: failed to issue tokens")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login temporarily unavailable. Please try again.",
        ) from None

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/api/auth",
        max_age=60 * 60 * 24 * 30,
    )
    return TokenResponse(access_token=access)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        payload = decode_token(token)
        if payload.get("typ") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        uid = payload.get("uid")
        if not uid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        user_id = uuid.UUID(uid)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Single-session: reject refresh if session was invalidated (new login)
    current_ver = getattr(user, "token_version", 0)
    token_ver = payload.get("ver", 0)
    if token_ver != current_ver:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired because your account was signed in somewhere else.",
        )

    access = create_access_token(subject=user.username, user_id=str(user.id), token_version=current_ver)
    refresh = create_refresh_token(subject=user.username, user_id=str(user.id), token_version=current_ver)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/api/auth",
        max_age=60 * 60 * 24 * 30,
    )
    return TokenResponse(access_token=access)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return _me_response(current_user)


@router.patch("/profile", response_model=MeResponse)
def patch_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    current_user.profile_name = payload.profile_name
    db.commit()
    db.refresh(current_user)
    return _me_response(current_user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if payload.new_password != payload.confirm_new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")
    if not verify_password(payload.current_password.strip(), current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}

