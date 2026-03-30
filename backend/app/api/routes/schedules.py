from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.ai_access import AI_FEATURES_FORBIDDEN_DETAIL, AI_SCHEDULE_TYPES
from app.core.feature_access import can_access_feature, feature_key_for_schedule_type
from app.core.limits import (
    MAX_ACTIVE_SCHEDULES,
    MAX_SAVED_SCHEDULES,
    MSG_MAX_ACTIVE_SCHEDULES,
    MSG_MAX_SAVED_SCHEDULES,
)
from app.db.session import get_db
from app.models.monitoring import MonitoringRun, MonitoringSchedule
from app.models.portfolio import PortfolioEntity
from app.models.user import User
from app.models.monitoring import SCHEDULE_TYPES
from app.schemas.schedules import EntityLabel, MODEL_OPTIONS, ScheduleCreate, ScheduleOut
from app.worker.tasks import trigger_monitoring_run


router = APIRouter()


def _to_out(s: MonitoringSchedule, entity_labels: list[EntityLabel] | None = None) -> ScheduleOut:
    group_ids = [x for x in (s.group_ids_csv or "").split(",") if x.strip()]
    entity_ids = [x for x in (getattr(s, "entity_ids_csv", None) or "").split(",") if x.strip()]
    linked = [x for x in (getattr(s, "linked_assets_csv", None) or "").split(",") if x.strip()]
    return ScheduleOut(
        id=str(s.id),
        name=s.name,
        cron=s.cron,
        group_ids=group_ids,
        entity_ids=entity_ids,
        entity_labels=entity_labels or [],
        bucket_minutes=s.bucket_minutes,
        is_active=s.is_active,
        status=s.status,
        schedule_type=getattr(s, "schedule_type", None) or "standard_monitor",
        label=getattr(s, "label", None),
        model=getattr(s, "model", None),
        impact_threshold=getattr(s, "impact_threshold", None),
        linked_assets=linked,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _resolve_entity_labels(db: Session, entity_ids: list[str], user_id: uuid.UUID) -> list[EntityLabel]:
    """Resolve entity ids to (id, name, symbol) for schedule display. Order matches entity_ids."""
    if not entity_ids:
        return []
    from sqlalchemy.orm import selectinload
    ids = []
    for eid_str in entity_ids:
        try:
            ids.append(uuid.UUID(eid_str))
        except ValueError:
            continue
    entities = db.scalars(
        select(PortfolioEntity)
        .where(PortfolioEntity.id.in_(ids), PortfolioEntity.user_id == user_id)
        .options(selectinload(PortfolioEntity.instrument))
    ).all()
    by_id = {e.id: e for e in entities}
    out = []
    for eid in ids:
        e = by_id.get(eid)
        if not e:
            continue
        symbol = (e.instrument.symbol if e.instrument else e.name)[:20]
        out.append(EntityLabel(id=str(e.id), name=e.name, symbol=symbol))
    return out


@router.get("", response_model=list[ScheduleOut])
def list_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ScheduleOut]:
    schedules = db.scalars(
        select(MonitoringSchedule)
        .where(MonitoringSchedule.user_id == current_user.id)
        .order_by(MonitoringSchedule.created_at.desc())
    ).all()
    result = []
    for s in schedules:
        entity_ids = [x for x in (getattr(s, "entity_ids_csv", None) or "").split(",") if x.strip()]
        labels = _resolve_entity_labels(db, entity_ids, current_user.id)
        result.append(_to_out(s, entity_labels=labels))
    return result


def _count_schedules(db: Session, user_id: uuid.UUID, active_only: bool = False) -> int:
    stmt = select(func.count()).select_from(MonitoringSchedule).where(MonitoringSchedule.user_id == user_id)
    if active_only:
        stmt = stmt.where(
            MonitoringSchedule.is_active.is_(True),
            MonitoringSchedule.status == "active",
        )
    return db.scalar(stmt) or 0


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScheduleOut:
    total = _count_schedules(db, current_user.id, active_only=False)
    if total >= MAX_SAVED_SCHEDULES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_MAX_SAVED_SCHEDULES)
    if payload.is_active:
        active = _count_schedules(db, current_user.id, active_only=True)
        if active >= MAX_ACTIVE_SCHEDULES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_MAX_ACTIVE_SCHEDULES)
    schedule_type = (payload.schedule_type or "standard_monitor").strip()
    if schedule_type not in SCHEDULE_TYPES:
        schedule_type = "standard_monitor"
    if schedule_type in AI_SCHEDULE_TYPES and not can_access_feature(
        current_user, feature_key_for_schedule_type(schedule_type)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AI_FEATURES_FORBIDDEN_DETAIL)
    model = (payload.model or "").strip() or None
    if model and model not in MODEL_OPTIONS:
        model = None
    linked_assets_csv = ",".join((payload.linked_assets or []))

    entity_ids_csv = ",".join((payload.entity_ids or []))
    if payload.entity_ids:
        for eid_str in payload.entity_ids:
            try:
                eid = uuid.UUID(eid_str)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid entity_id: {eid_str}")
            ent = db.scalar(
                select(PortfolioEntity).where(
                    PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id
                )
            )
            if not ent:
                raise HTTPException(status_code=404, detail=f"Entity not found: {eid_str}")
    schedule = MonitoringSchedule(
        user_id=current_user.id,
        name=payload.name,
        cron=payload.cron,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        schedule_type=schedule_type,
        label=(payload.label or "").strip() or None,
        model=model,
        impact_threshold=payload.impact_threshold,
        linked_assets_csv=linked_assets_csv,
        group_ids_csv=",".join(payload.group_ids or []),
        entity_ids_csv=entity_ids_csv,
        bucket_minutes=payload.bucket_minutes,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    labels = _resolve_entity_labels(db, payload.entity_ids or [], current_user.id)
    return _to_out(schedule, entity_labels=labels)


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid schedule id")
    schedule = db.scalar(
        select(MonitoringSchedule).where(MonitoringSchedule.id == sid, MonitoringSchedule.user_id == current_user.id)
    )
    if not schedule:
        return {"ok": True, "deleted": False}
    try:
        db.execute(delete(MonitoringRun).where(MonitoringRun.schedule_id == sid))
        db.delete(schedule)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Schedule deletion failed: {e!s}",
        ) from e
    return {"ok": True, "deleted": True}


@router.post("/{schedule_id}/pause", status_code=status.HTTP_200_OK, response_model=ScheduleOut)
def pause_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScheduleOut:
    sid = uuid.UUID(schedule_id)
    schedule = db.scalar(
        select(MonitoringSchedule).where(MonitoringSchedule.id == sid, MonitoringSchedule.user_id == current_user.id)
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Not found")
    schedule.status = "paused"
    schedule.is_active = False
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    entity_ids = [x for x in (getattr(schedule, "entity_ids_csv", None) or "").split(",") if x.strip()]
    return _to_out(schedule, entity_labels=_resolve_entity_labels(db, entity_ids, current_user.id))


@router.post("/{schedule_id}/resume", status_code=status.HTTP_200_OK, response_model=ScheduleOut)
def resume_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScheduleOut:
    sid = uuid.UUID(schedule_id)
    schedule = db.scalar(
        select(MonitoringSchedule).where(MonitoringSchedule.id == sid, MonitoringSchedule.user_id == current_user.id)
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Not found")
    active = _count_schedules(db, current_user.id, active_only=True)
    if active >= MAX_ACTIVE_SCHEDULES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_MAX_ACTIVE_SCHEDULES)
    schedule.status = "active"
    schedule.is_active = True
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    entity_ids = [x for x in (getattr(schedule, "entity_ids_csv", None) or "").split(",") if x.strip()]
    return _to_out(schedule, entity_labels=_resolve_entity_labels(db, entity_ids, current_user.id))


@router.post("/{schedule_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_now(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    sid = uuid.UUID(schedule_id)
    schedule = db.scalar(
        select(MonitoringSchedule).where(MonitoringSchedule.id == sid, MonitoringSchedule.user_id == current_user.id)
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Not found")
    trigger_monitoring_run.delay(user_id=str(current_user.id), schedule_id=str(schedule.id))
    return {"status": "queued"}

