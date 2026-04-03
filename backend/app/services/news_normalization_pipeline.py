from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument
from app.models.document import SourceDocument
from app.models.portfolio import PortfolioEntity
from app.services.cache_fallback import utcnow
from app.services.entity_news_service import build_target_news_query, fetch_entity_news_by_query
from app.services.entity_metrics_pipeline import coverage_from_deduped_docs

logger = logging.getLogger(__name__)


def _norm_title(title: str) -> str:
    t = (title or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _fingerprint(title: str) -> str:
    nt = _norm_title(title).lower()
    # keep only word-ish chars for stable cross-source matching
    nt = re.sub(r"[^a-z0-9\s\-_/]+", "", nt)
    nt = re.sub(r"\s+", " ", nt).strip()
    return hashlib.sha256(nt.encode("utf-8")).hexdigest()[:64]


_UUID_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # NAMESPACE_DNS


def _cluster_id(fp: str) -> uuid.UUID:
    return uuid.uuid5(_UUID_NS, fp)


def _safe_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    s = str(iso).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def upsert_normalized_news_for_entity(
    db: Session,
    *,
    entity: PortfolioEntity,
    lookback_days: int = 2,
    limit: int = 80,
) -> dict[str, int]:
    """
    Minimal real pipeline:
    - Pull Google News RSS for target query (symbol/name)
    - Normalize and dedupe by canonical_url (unique) + fingerprint clustering
    - Write NormalizedNewsDocument rows (and a lightweight SourceDocument trace row)
    - Update EntityDailyMetric.coverage_volume using article counts per day (with low-quality filtering)
    """
    if not entity or not entity.id:
        return {"fetched": 0, "normalized_written": 0, "raw_written": 0, "coverage_days_updated": 0}

    q = build_target_news_query(entity)
    if not q:
        return {"fetched": 0, "normalized_written": 0, "raw_written": 0, "coverage_days_updated": 0}

    items, _q_used, err, _cache = fetch_entity_news_by_query(entity_id=str(entity.id), query=q, limit=limit)
    if err:
        return {"fetched": 0, "normalized_written": 0, "raw_written": 0, "coverage_days_updated": 0}

    fetched = len(items)
    if not items:
        return {"fetched": 0, "normalized_written": 0, "raw_written": 0, "coverage_days_updated": 0}

    # consider only recent items (published_at may be null)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(lookback_days)))
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = _norm_title(str(it.get("title") or "").strip())
        url = str(it.get("url") or "").strip()
        src = str(it.get("source") or "News").strip()[:60]
        pub = _safe_dt(it.get("published_at"))
        if pub and pub < cutoff:
            continue
        if not title or not url:
            continue
        fp = _fingerprint(title)
        rows.append(
            {
                "title": title[:512],
                "url": url[:2048],
                "source": src,
                "published_at": pub,
                "fingerprint": fp,
                "cluster_id": _cluster_id(fp),
                "raw": it,
            }
        )

    if not rows:
        return {"fetched": fetched, "normalized_written": 0, "raw_written": 0, "coverage_days_updated": 0}

    # Dedup within batch by canonical_url
    uniq_by_url: dict[str, dict[str, Any]] = {}
    for r in rows:
        uniq_by_url.setdefault(r["url"], r)
    urls = list(uniq_by_url.keys())

    existing = set(
        db.scalars(
            select(NormalizedNewsDocument.canonical_url).where(NormalizedNewsDocument.canonical_url.in_(urls))
        ).all()
    )

    normalized_written = 0
    raw_written = 0
    now = utcnow()

    for url in urls:
        if url in existing:
            continue
        r = uniq_by_url[url]
        # Raw trace row (minimal): SourceDocument
        source_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:48]
        doc_id = db.scalar(
            select(SourceDocument.id).where(
                SourceDocument.user_id == entity.user_id,
                SourceDocument.source == "google_news_rss",
                SourceDocument.source_id == source_id,
            )
        )
        if not doc_id:
            doc = SourceDocument(
                user_id=entity.user_id,
                source="google_news_rss",
                source_id=source_id,
                url=url,
                title=r["title"],
                content=str((r.get("raw") or {}).get("snippet") or "")[:4000] or None,
                published_at=r["published_at"],
                extra={"entity_id": str(entity.id), "source_name": r["source"]},
            )
            db.add(doc)
            try:
                # Use a SAVEPOINT so a single bad row never rolls back the whole batch.
                with db.begin_nested():
                    db.flush()
                raw_written += 1
                doc_id = doc.id
            except Exception:
                logger.debug("raw SourceDocument insert failed (ignored) url=%s", url, exc_info=True)
                doc_id = None

        nd = NormalizedNewsDocument(
            canonical_url=url,
            normalized_title=r["title"],
            title_fingerprint=r["fingerprint"],
            source_channel="google_news_rss",
            entity_id=entity.id,
            keyword_group_id=None,
            published_at=r["published_at"],
            dedup_cluster_id=r["cluster_id"],
            raw_sources={"source": r["source"], "raw": r.get("raw"), "source_document_id": str(doc_id) if doc_id else None},
            created_at=now,
        )
        db.add(nd)
        try:
            with db.begin_nested():
                db.flush()
            normalized_written += 1
        except IntegrityError:
            continue

    # Update coverage_volume for recent days based on stored normalized docs
    coverage_days_updated = 0
    # Use UTC day boundaries to match published_at storage and coverage queries.
    today = utcnow().date()
    for i in range(max(1, int(lookback_days)) + 1):
        d = today - timedelta(days=i - 1)
        c = coverage_from_deduped_docs(db, entity.id, d)
        if c is None:
            continue
        row = db.scalar(
            select(EntityDailyMetric).where(
                EntityDailyMetric.entity_id == entity.id,
                EntityDailyMetric.metric_date == d,
            )
        )
        if row is None:
            row = EntityDailyMetric(
                entity_id=entity.id,
                metric_date=d,
                search_trend=None,
                coverage_volume=float(c),
                sentiment_score=None,
                coverage_volume_source="real",
                search_trend_source=None,
                last_success_at=now,
                last_error=None,
                is_stale=False,
            )
            db.add(row)
        else:
            row.coverage_volume = float(c)
            row.coverage_volume_source = "real"
            row.last_success_at = now
            row.last_error = None
            row.is_stale = False
        coverage_days_updated += 1

    return {
        "fetched": fetched,
        "normalized_written": normalized_written,
        "raw_written": raw_written,
        "coverage_days_updated": coverage_days_updated,
    }


def pick_entity_candidates(db: Session, *, limit: int = 25) -> list[PortfolioEntity]:
    """
    Minimal candidate selection:
    - entities with an instrument bound
    - newest first (bias toward recently added/edited)
    """
    rows = db.scalars(
        select(PortfolioEntity)
        .where(PortfolioEntity.instrument_id.isnot(None))
        .order_by(PortfolioEntity.updated_at.desc().nullslast(), PortfolioEntity.created_at.desc())
        .limit(int(limit))
        .options(selectinload(PortfolioEntity.instrument), selectinload(PortfolioEntity.terms))
    ).all()
    return list(rows)

