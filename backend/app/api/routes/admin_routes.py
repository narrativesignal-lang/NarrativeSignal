"""Admin-only routes: user management, etc."""

from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_admin, user_is_admin
from app.db.session import get_db
from app.models.portfolio import PortfolioEntity
from app.models.system_runtime_flag import SystemRuntimeFlag
from app.models.system_runtime_log import SystemRuntimeLog
from app.models.user import User
from app.services.entity_metrics_pipeline import sync_entity_search_trend
from app.services.runtime_flags import DEFAULTS, RuntimeFlagKey, load_all_flags, pytrends_enabled
from app.services.runtime_logs import list_recent_runtime_logs
from sqlalchemy.exc import IntegrityError


router = APIRouter(dependencies=[])


class AdminUserPatchBody(BaseModel):
    paid_access: bool | None = None


class AdminUsersBulkDeleteBody(BaseModel):
    user_ids: list[str]


def _obvious_test_user(u: User) -> bool:
    em = (u.email or "").lower()
    un = (u.username or "").lower()
    if em.endswith("@example.com"):
        return True
    for p in ("burst_", "e2e_", "auth_e2e_", "loadtest_", "test_user_", "playwright_"):
        if un.startswith(p):
            return True
    if "e2e" in un or "e2e" in em:
        return True
    return False


class RuntimeFlagOut(BaseModel):
    key: str
    value_bool: bool
    updated_at: str | None = None
    updated_by: str | None = None


class RuntimeFlagPatchBody(BaseModel):
    value_bool: bool


class RuntimeLogOut(BaseModel):
    created_at: str
    level: str
    category: str
    job_name: str | None = None
    provider: str | None = None
    status: str | None = None
    message: str
    disabled_by_runtime_flag: bool
    no_provider_call: bool
    request_count: int | None = None
    fallback_count: int | None = None
    symbol_count: int | None = None


@router.get("/users")
def list_users(
    include_load_test: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[dict]:
    """List all users (admin only). Includes username, role, created_at, session/plan info."""
    stmt = select(User).order_by(User.created_at.desc())
    if not include_load_test:
        # Local DBs are often polluted by load-test registrations like burst_*@example.com.
        # Hide by default so Admin/Users remains usable; admin can opt in.
        stmt = stmt.where(~User.email.ilike("burst_%@example.com"))
    rows = db.execute(stmt).scalars().all()
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


@router.delete("/users/bulk")
def bulk_delete_users(
    payload: AdminUsersBulkDeleteBody = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, int]:
    deleted = 0
    seen: set[uuid.UUID] = set()
    for raw in payload.user_ids or []:
        try:
            uid = uuid.UUID(str(raw).strip())
        except ValueError:
            continue
        if uid in seen:
            continue
        seen.add(uid)
        if uid == admin.id:
            continue
        u = db.get(User, uid)
        if not u:
            continue
        db.delete(u)
        deleted += 1
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Delete blocked by FK constraints: {str(e.orig)[:200]}") from e
    return {"deleted": deleted}


@router.post("/users/delete-obvious-test-users")
def delete_obvious_test_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, int]:
    candidates = [u.id for u in db.scalars(select(User).where(User.id != admin.id)).all() if _obvious_test_user(u)]
    deleted = 0
    for uid in candidates:
        u = db.get(User, uid)
        if not u:
            continue
        db.delete(u)
        deleted += 1
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Delete blocked by FK constraints: {str(e.orig)[:200]}") from e
    return {"deleted": deleted}


@router.post("/metrics/sync-search-trends")
def admin_sync_search_trends(
    entity_id: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, int]:
    if not pytrends_enabled(db):
        raise HTTPException(
            status_code=503,
            detail="Search trend sync is disabled (ENABLE_PYTRENDS runtime flag).",
        )
    total_rows = 0
    n_entities = 0
    if entity_id and str(entity_id).strip():
        eid = uuid.UUID(str(entity_id).strip())
        entity = db.scalar(
            select(PortfolioEntity).where(PortfolioEntity.id == eid).options(selectinload(PortfolioEntity.terms))
        )
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        if not entity.terms:
            return {"entities": 0, "metric_rows": 0}
        total_rows = sync_entity_search_trend(db, eid, timeframe="today 3-m")
        if total_rows == 0 and entity.terms:
            total_rows = sync_entity_search_trend(db, eid, timeframe="today 6-m")
        n_entities = 1
    else:
        for entity in db.scalars(select(PortfolioEntity).options(selectinload(PortfolioEntity.terms))).all():
            if not entity.terms:
                continue
            r = sync_entity_search_trend(db, entity.id, timeframe="today 3-m")
            if r == 0 and entity.terms:
                r = sync_entity_search_trend(db, entity.id, timeframe="today 6-m")
            total_rows += r
            n_entities += 1
    db.commit()
    return {"entities": n_entities, "metric_rows": total_rows}


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


@router.get("/runtime-flags", response_model=list[RuntimeFlagOut])
def list_runtime_flags(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> list[RuntimeFlagOut]:
    """
    Runtime flags (admin only). These override env/config defaults and take effect without restart.
    """
    vals = load_all_flags(db, use_cache=False)
    rows = {r.key: r for r in db.execute(select(SystemRuntimeFlag)).scalars().all()}
    outs: list[RuntimeFlagOut] = []
    for k in sorted(vals.keys()):
        r = rows.get(k)
        outs.append(
            RuntimeFlagOut(
                key=k,
                value_bool=bool(vals[k]),
                updated_at=r.updated_at.isoformat() if r and r.updated_at else None,
                updated_by=r.updated_by if r else None,
            )
        )
    return outs


@router.patch("/runtime-flags/{key}", response_model=RuntimeFlagOut)
def patch_runtime_flag(
    key: str,
    payload: RuntimeFlagPatchBody,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RuntimeFlagOut:
    k = (key or "").strip().upper()
    if not k:
        raise HTTPException(status_code=400, detail="Invalid key")

    # allowlist first batch; keep tight so random keys aren't silently accepted.
    allowed = set(DEFAULTS.keys())
    if k not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown runtime flag: {k}")

    row = db.get(SystemRuntimeFlag, k)
    if row is None:
        row = SystemRuntimeFlag(key=k)
        db.add(row)
    row.value_bool = bool(payload.value_bool)
    row.updated_by = getattr(admin, "email", None) or getattr(admin, "username", None) or str(getattr(admin, "id", "") or "") or "admin"
    # updated_at handled by DB/onupdate; set explicit for sqlite parity
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    return RuntimeFlagOut(
        key=row.key,
        value_bool=bool(row.value_bool),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        updated_by=row.updated_by,
    )


@router.get("/runtime-logs", response_model=list[RuntimeLogOut])
def get_runtime_logs(
    limit: int = 50,
    category: str | None = None,
    min_level: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[RuntimeLogOut]:
    rows: list[SystemRuntimeLog] = list_recent_runtime_logs(db, limit=limit, category=category, min_level=min_level)
    return [
        RuntimeLogOut(
            created_at=r.created_at.isoformat() if r.created_at else "",
            level=r.level,
            category=r.category,
            job_name=r.job_name,
            provider=r.provider,
            status=r.status,
            message=r.message,
            disabled_by_runtime_flag=bool(r.disabled_by_runtime_flag),
            no_provider_call=bool(r.no_provider_call),
            request_count=r.request_count,
            fallback_count=r.fallback_count,
            symbol_count=r.symbol_count,
        )
        for r in rows
    ]
