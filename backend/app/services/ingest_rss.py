from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import SourceDocument
from app.models.group_document import GroupDocument
from app.models.rss_feed import KeywordGroupRssFeed
from app.services.analysis import _matches_group  # reuse matcher for fallback feeds only


DEFAULT_RSS_FEEDS: list[str] = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.ft.com/?format=rss",
]


def ingest_rss_for_user(*, db: Session, user_id, lookback_hours: int = 48, feeds: list[str] | None = None) -> int:
    """
    Legacy helper: ingest RSS feeds without group linkage.
    """
    feeds = feeds or DEFAULT_RSS_FEEDS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    created = 0

    for feed_url in feeds:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:200]:
            source_id = getattr(entry, "id", None) or getattr(entry, "link", None) or getattr(entry, "title", None)
            if not source_id:
                continue

            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published and published < cutoff:
                continue

            exists = db.scalar(
                select(SourceDocument.id).where(
                    SourceDocument.user_id == user_id, SourceDocument.source == "rss", SourceDocument.source_id == source_id
                )
            )
            if exists:
                continue

            doc = SourceDocument(
                user_id=user_id,
                source="rss",
                source_id=str(source_id)[:255],
                url=getattr(entry, "link", None),
                title=getattr(entry, "title", None),
                content=getattr(entry, "summary", None),
                published_at=published,
                extra={"feed": feed_url},
            )
            db.add(doc)
            db.commit()
            created += 1

    return created


def ingest_rss_for_group(
    *,
    db: Session,
    user_id,
    group,
    lookback_hours: int = 48,
) -> tuple[int, int, list[uuid.UUID]]:
    """
    Group-aware RSS ingestion.

    Returns (documents_created, links_created, newly_linked_document_ids).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    feed_rows = db.scalars(
        select(KeywordGroupRssFeed).where(
            KeywordGroupRssFeed.user_id == user_id,
            KeywordGroupRssFeed.group_id == group.id,
            KeywordGroupRssFeed.is_active.is_(True),
        )
    ).all()
    feeds = [f.url for f in feed_rows] if feed_rows else DEFAULT_RSS_FEEDS

    docs_created = 0
    links_created = 0
    newly_linked: list[uuid.UUID] = []

    for feed_url in feeds:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:200]:
            source_id = getattr(entry, "id", None) or getattr(entry, "link", None) or getattr(entry, "title", None)
            if not source_id:
                continue

            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published and published < cutoff:
                continue

            # Create or get SourceDocument
            doc_id = db.scalar(
                select(SourceDocument.id).where(
                    SourceDocument.user_id == user_id, SourceDocument.source == "rss", SourceDocument.source_id == str(source_id)[:255]
                )
            )
            if not doc_id:
                doc = SourceDocument(
                    user_id=user_id,
                    source="rss",
                    source_id=str(source_id)[:255],
                    url=getattr(entry, "link", None),
                    title=getattr(entry, "title", None),
                    content=getattr(entry, "summary", None),
                    published_at=published,
                    extra={"feed": feed_url},
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)
                doc_id = doc.id
                docs_created += 1

            # Link to group (for default feeds, enforce keyword match to avoid noise)
            if not feed_rows:
                d = db.get(SourceDocument, doc_id)
                text = " ".join([d.title or "", d.content or ""])
                if not _matches_group(text, group):
                    continue

            existing_link = db.scalar(
                select(GroupDocument.id).where(GroupDocument.group_id == group.id, GroupDocument.document_id == doc_id)
            )
            if existing_link:
                continue

            link = GroupDocument(group_id=group.id, document_id=doc_id, matched_terms={})
            db.add(link)
            db.commit()
            links_created += 1
            newly_linked.append(doc_id)

    return docs_created, links_created, newly_linked

