"""Entity-scoped Google News RSS (short cache, deduped list for UI)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote_plus

import redis

from app.core.config import settings
from app.models.portfolio import Instrument, PortfolioEntity
from app.services.macro_news import MacroNewsItem, _items_from_feed_url
from app.services.macro_news_dedup import finalize_macro_news_list

logger = logging.getLogger(__name__)

CACHE_PREFIX = "entity_news:v1:"
TIMELINE_CACHE_PREFIX = "entity_news:timeline:v1:"
CACHE_TTL_SEC = 600  # 10 minutes
FETCH_TIMEOUT = 8.0


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _google_rss_url(q: str, *, when: str = "7d") -> str:
    encoded = quote_plus((q or "").strip())
    return f"https://news.google.com/rss/search?q={encoded}+when:{when}&hl=en-US&gl=US&ceid=US:en"


def build_target_news_query(entity: PortfolioEntity) -> str | None:
    """Instrument symbol + name + entity name, biased toward corporate/market headlines."""
    chunks: list[str] = []
    inst: Instrument | None = entity.instrument
    if inst:
        sym = (inst.symbol or "").strip()
        if sym:
            chunks.append(sym)
        dn = (inst.display_name or "").strip()
        if dn and sym and dn.upper() != sym.upper():
            chunks.append(dn)
        elif dn and not sym:
            chunks.append(dn)
    name = (entity.name or "").strip()
    if name:
        low = name.lower()
        if not any(low == (c or "").lower() for c in chunks):
            chunks.append(name)
    if not chunks:
        return None
    base = " ".join(chunks[:4])
    ac = (inst.asset_class or "").lower() if inst else ""
    if "crypto" in ac or "future" in ac:
        return f"{base} market"
    return f"{base} stock OR {base} earnings"


def build_keyword_news_query(terms: list[str]) -> str | None:
    clean = [t.strip() for t in terms if t and t.strip()]
    if not clean:
        return None
    tail = clean[:10]
    if len(tail) == 1:
        return tail[0]
    return " OR ".join(tail[:8])


def _items_to_payload(items: list[MacroNewsItem], *, matched_by: Literal["target", "keyword"]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        ts = it.timestamp
        out.append(
            {
                "title": it.title,
                "source": it.source,
                "published_at": ts.isoformat() if ts else None,
                "url": it.url,
                "snippet": (it.summary or None),
                "matched_by": matched_by,
            }
        )
    return out


def fetch_entity_news(
    *,
    entity_id: str,
    entity: PortfolioEntity,
    mode: Literal["target", "keywords"],
    limit: int = 24,
) -> tuple[list[dict[str, Any]], str | None, str | None, bool]:
    """
    Returns (items, query_used, error_message, cache_hit).
    """
    matched: Literal["target", "keyword"] = "target" if mode == "target" else "keyword"
    query: str | None
    if mode == "target":
        query = build_target_news_query(entity)
        if not query:
            return [], None, None, False
    else:
        term_strings = [t.term for t in (entity.terms or [])]
        query = build_keyword_news_query(term_strings)
        if not query:
            return [], None, "no_keywords", False

    cache_key = CACHE_PREFIX + hashlib.sha256(f"{entity_id}:{mode}:{query}".encode()).hexdigest()
    try:
        raw = _r().get(cache_key)
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"], data.get("query") or query, None, True
            if isinstance(data, list):
                return data, query, None, True
    except Exception as e:
        logger.debug("entity_news cache read failed: %s", e)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    feed_url = _google_rss_url(query, when="7d")
    try:
        batch = _items_from_feed_url(
            "entity",
            mode,
            feed_url,
            now=now,
            cutoff=cutoff,
            timeout=FETCH_TIMEOUT,
        )
    except Exception as e:
        logger.warning("entity_news fetch failed entity_id=%s mode=%s err=%s", entity_id, mode, e)
        return [], query, "fetch_failed", False

    try:
        final = finalize_macro_news_list(batch, min(limit, 40))
    except Exception as e:
        logger.warning("entity_news dedup failed: %s", e)
        batch.sort(key=lambda x: x.timestamp, reverse=True)
        final = batch[:limit]

    payload = _items_to_payload(final, matched_by=matched)
    try:
        _r().setex(
            cache_key,
            CACHE_TTL_SEC,
            json.dumps({"query": query, "items": payload}, default=str),
        )
    except Exception as e:
        logger.debug("entity_news cache write failed: %s", e)

    return payload, query, None, False


def fetch_entity_news_by_query(
    *,
    entity_id: str,
    query: str,
    limit: int = 60,
    cache_prefix: str = TIMELINE_CACHE_PREFIX,
) -> tuple[list[dict[str, Any]], str | None, str | None, bool]:
    """
    Google News RSS for an explicit query string (timeline volatility / official windows).
    Separate cache namespace from mode-based entity_news fetches.
    """
    q = (query or "").strip()
    if not q:
        return [], None, "empty_query", False

    cache_key = cache_prefix + hashlib.sha256(f"{entity_id}:{q}".encode()).hexdigest()
    try:
        raw = _r().get(cache_key)
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"], data.get("query") or q, None, True
            if isinstance(data, list):
                return data, q, None, True
    except Exception as e:
        logger.debug("entity_news_by_query cache read failed: %s", e)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    feed_url = _google_rss_url(q, when="7d")
    try:
        batch = _items_from_feed_url(
            "entity",
            "timeline_query",
            feed_url,
            now=now,
            cutoff=cutoff,
            timeout=FETCH_TIMEOUT,
        )
    except Exception as e:
        logger.warning("entity_news_by_query fetch failed entity_id=%s err=%s", entity_id, e)
        return [], q, "fetch_failed", False

    try:
        final = finalize_macro_news_list(batch, min(limit, 80))
    except Exception as e:
        logger.warning("entity_news_by_query dedup failed: %s", e)
        batch.sort(key=lambda x: x.timestamp, reverse=True)
        final = batch[:limit]

    payload = _items_to_payload(final, matched_by="keyword")
    try:
        _r().setex(
            cache_key,
            CACHE_TTL_SEC,
            json.dumps({"query": q, "items": payload}, default=str),
        )
    except Exception as e:
        logger.debug("entity_news_by_query cache write failed: %s", e)

    return payload, q, None, False
