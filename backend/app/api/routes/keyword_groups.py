from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document_analysis import DocumentAnalysis
from app.models.entity_config import EntityConfig
from app.models.group_asset import GroupAssetLink
from app.models.group_document import GroupDocument
from app.models.index_point import IndexPoint
from app.models.keyword_group import KeywordGroup, KeywordTerm
from app.models.rss_feed import KeywordGroupRssFeed
from app.models.spike_event import SpikeEvent
from app.models.user import User
from app.schemas.keyword_groups import KeywordGroupCreate, KeywordGroupOut, KeywordGroupUpdate, KeywordTermOut
from app.services.subscriptions import register_keyword_group_subscriptions


router = APIRouter()


def _to_out(group: KeywordGroup) -> KeywordGroupOut:
    return KeywordGroupOut(
        id=str(group.id),
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        terms=[KeywordTermOut(id=str(t.id), term=t.term, is_required=t.is_required) for t in group.terms],
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("", response_model=list[KeywordGroupOut])
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KeywordGroupOut]:
    groups = db.scalars(
        select(KeywordGroup).where(KeywordGroup.user_id == current_user.id).order_by(KeywordGroup.created_at.desc())
    ).all()
    return [_to_out(g) for g in groups]


@router.post("", response_model=KeywordGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: KeywordGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KeywordGroupOut:
    group = KeywordGroup(user_id=current_user.id, name=payload.name, description=payload.description)
    for term in payload.terms:
        group.terms.append(KeywordTerm(term=term.term, is_required=term.is_required))
    db.add(group)
    db.flush()
    register_keyword_group_subscriptions(db, current_user.id, group.id)
    db.commit()
    db.refresh(group)
    return _to_out(group)


@router.get("/{group_id}", response_model=KeywordGroupOut)
def get_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KeywordGroupOut:
    gid = uuid.UUID(group_id)
    group = db.scalar(select(KeywordGroup).where(KeywordGroup.id == gid, KeywordGroup.user_id == current_user.id))
    if not group:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_out(group)


@router.put("/{group_id}", response_model=KeywordGroupOut)
def update_group(
    group_id: str,
    payload: KeywordGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KeywordGroupOut:
    gid = uuid.UUID(group_id)
    group = db.scalar(select(KeywordGroup).where(KeywordGroup.id == gid, KeywordGroup.user_id == current_user.id))
    if not group:
        raise HTTPException(status_code=404, detail="Not found")

    if payload.name is not None:
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    if payload.is_active is not None:
        group.is_active = payload.is_active

    if payload.terms is not None:
        group.terms.clear()
        for term in payload.terms:
            group.terms.append(KeywordTerm(term=term.term, is_required=term.is_required))

    db.add(group)
    db.commit()
    db.refresh(group)
    return _to_out(group)


@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    gid = uuid.UUID(group_id)
    group = db.scalar(select(KeywordGroup).where(KeywordGroup.id == gid, KeywordGroup.user_id == current_user.id))
    if not group:
        return None
    # Manually delete dependents to satisfy FK constraints (no DB-level ON DELETE CASCADE)
    db.query(GroupDocument).filter(GroupDocument.group_id == gid).delete(synchronize_session=False)
    db.query(IndexPoint).filter(IndexPoint.group_id == gid).delete(synchronize_session=False)
    db.query(GroupAssetLink).filter(GroupAssetLink.group_id == gid).delete(synchronize_session=False)
    db.query(EntityConfig).filter(EntityConfig.group_id == gid).delete(synchronize_session=False)
    db.query(DocumentAnalysis).filter(DocumentAnalysis.group_id == gid).delete(synchronize_session=False)
    db.query(KeywordGroupRssFeed).filter(KeywordGroupRssFeed.group_id == gid).delete(synchronize_session=False)
    db.query(SpikeEvent).filter(SpikeEvent.group_id == gid).delete(synchronize_session=False)
    db.delete(group)
    db.commit()
    return None

