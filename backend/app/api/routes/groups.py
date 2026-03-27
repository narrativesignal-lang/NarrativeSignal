from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document import SourceDocument
from app.models.document_analysis import DocumentAnalysis
from app.models.entity_config import EntityConfig
from app.models.group_asset import GroupAssetLink
from app.models.group_document import GroupDocument
from app.models.keyword_group import KeywordGroup
from app.models.rss_feed import KeywordGroupRssFeed
from app.models.spike_event import SpikeEvent
from app.models.user import User
from app.schemas.assets import GroupAssetOut, GroupAssetUpsert
from app.schemas.entity_config import EntityConfigOut, EntityConfigUpdate
from app.schemas.group_articles import GroupArticleOut, GroupArticlesResponse
from app.schemas.rss_feeds import RssFeedCreate, RssFeedOut


router = APIRouter()


def _require_group(db: Session, user_id: uuid.UUID, group_id: uuid.UUID) -> KeywordGroup:
    group = db.scalar(select(KeywordGroup).where(KeywordGroup.id == group_id, KeywordGroup.user_id == user_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.get("/{group_id}/feeds", response_model=list[RssFeedOut])
def list_feeds(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RssFeedOut]:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    feeds = db.scalars(
        select(KeywordGroupRssFeed)
        .where(KeywordGroupRssFeed.group_id == gid, KeywordGroupRssFeed.user_id == current_user.id)
        .order_by(KeywordGroupRssFeed.created_at.desc())
    ).all()
    return [
        RssFeedOut(id=str(f.id), name=f.name, url=f.url, is_active=f.is_active, created_at=f.created_at) for f in feeds
    ]


@router.post("/{group_id}/feeds", response_model=RssFeedOut, status_code=status.HTTP_201_CREATED)
def add_feed(
    group_id: str,
    payload: RssFeedCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RssFeedOut:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    feed = KeywordGroupRssFeed(
        user_id=current_user.id, group_id=gid, name=payload.name, url=payload.url, is_active=payload.is_active
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return RssFeedOut(id=str(feed.id), name=feed.name, url=feed.url, is_active=feed.is_active, created_at=feed.created_at)


@router.delete("/{group_id}/feeds/{feed_id}", status_code=status.HTTP_200_OK)
def delete_feed(
    group_id: str,
    feed_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    gid = uuid.UUID(group_id)
    fid = uuid.UUID(feed_id)
    _require_group(db, current_user.id, gid)
    feed = db.scalar(
        select(KeywordGroupRssFeed).where(
            KeywordGroupRssFeed.id == fid, KeywordGroupRssFeed.group_id == gid, KeywordGroupRssFeed.user_id == current_user.id
        )
    )
    if not feed:
        return {"ok": True}
    db.delete(feed)
    db.commit()
    return {"ok": True}


@router.put("/{group_id}/asset", response_model=GroupAssetOut)
def upsert_asset(
    group_id: str,
    payload: GroupAssetUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupAssetOut:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    link = db.scalar(select(GroupAssetLink).where(GroupAssetLink.group_id == gid))
    if not link:
        link = GroupAssetLink(group_id=gid, symbol=payload.symbol.upper(), provider=payload.provider)
    else:
        link.symbol = payload.symbol.upper()
        link.provider = payload.provider
    db.add(link)
    db.commit()
    return GroupAssetOut(group_id=group_id, symbol=link.symbol, provider=link.provider)


@router.get("/{group_id}/asset", response_model=GroupAssetOut | None)
def get_asset(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupAssetOut | None:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    link = db.scalar(select(GroupAssetLink).where(GroupAssetLink.group_id == gid))
    if not link:
        return None
    return GroupAssetOut(group_id=group_id, symbol=link.symbol, provider=link.provider)


@router.get("/{group_id}/articles", response_model=GroupArticlesResponse)
def list_group_articles(
    group_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupArticlesResponse:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)

    links = db.scalars(
        select(GroupDocument).where(GroupDocument.group_id == gid).order_by(GroupDocument.created_at.desc()).limit(limit)
    ).all()
    doc_ids = [l.document_id for l in links]
    if not doc_ids:
        return GroupArticlesResponse(group_id=group_id, items=[])

    docs = db.scalars(select(SourceDocument).where(SourceDocument.id.in_(doc_ids))).all()
    docs_by_id = {d.id: d for d in docs}

    analyses = db.scalars(
        select(DocumentAnalysis)
        .where(DocumentAnalysis.group_id == gid, DocumentAnalysis.document_id.in_(doc_ids))
        .order_by(DocumentAnalysis.created_at.desc())
    ).all()
    analysis_by_doc: dict[uuid.UUID, DocumentAnalysis] = {}
    for a in analyses:
        analysis_by_doc.setdefault(a.document_id, a)

    items: list[GroupArticleOut] = []
    for l in links:
        d = docs_by_id.get(l.document_id)
        if not d:
            continue
        a = analysis_by_doc.get(d.id)
        items.append(
            GroupArticleOut(
                document_id=str(d.id),
                title=d.title,
                url=d.url,
                source=d.source,
                published_at=d.published_at,
                content=d.content,
                metadata=d.extra or {},
                sentiment_label=a.sentiment_label if a else None,
                sentiment_score=a.sentiment_score if a else None,
                narrative_summary=a.narrative_summary if a else None,
                detected_events=a.detected_events if a else None,
            )
        )
    return GroupArticlesResponse(group_id=group_id, items=items)


@router.get("/{group_id}/spikes")
def list_spikes(
    group_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    spikes = db.scalars(
        select(SpikeEvent).where(SpikeEvent.group_id == gid).order_by(SpikeEvent.bucket_start.desc()).limit(limit)
    ).all()
    return [
        {
            "id": str(s.id),
            "bucket_start": s.bucket_start,
            "kind": s.kind,
            "score": s.score,
            "details": s.details,
            "created_at": s.created_at,
        }
        for s in spikes
    ]


@router.get("/{group_id}/entity-config", response_model=EntityConfigOut)
def get_entity_config(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityConfigOut:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    row = db.scalar(
        select(EntityConfig).where(EntityConfig.group_id == gid, EntityConfig.user_id == current_user.id)
    )
    if not row:
        return EntityConfigOut(group_id=group_id, config={"charts": [], "market_data": []})
    return EntityConfigOut(group_id=group_id, config=row.config or {})


@router.put("/{group_id}/entity-config", response_model=EntityConfigOut)
def put_entity_config(
    group_id: str,
    payload: EntityConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityConfigOut:
    gid = uuid.UUID(group_id)
    _require_group(db, current_user.id, gid)
    row = db.scalar(
        select(EntityConfig).where(EntityConfig.group_id == gid, EntityConfig.user_id == current_user.id)
    )
    raw = payload.config if isinstance(payload.config, dict) else {}
    charts = raw.get("charts") if isinstance(raw.get("charts"), list) else []
    market_data = raw.get("market_data") if isinstance(raw.get("market_data"), list) else []
    config = {
        "charts": charts[:5],
        "market_data": market_data[:5],
    }
    if not row:
        row = EntityConfig(user_id=current_user.id, group_id=gid, config=config)
        db.add(row)
    else:
        row.config = config
    db.commit()
    db.refresh(row)
    return EntityConfigOut(group_id=group_id, config=row.config)

