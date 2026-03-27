"""
First-screen fallbacks for macro news when DB snapshot row is missing.

- Redis key stores last successful snapshot payload per category (JSON list of row dicts).
- In-memory seed headlines when neither DB nor Redis has content.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis

from app.core.config import settings
from app.schemas.macro import MacroNewsItemOut
from app.services.macro_news_dedup import ensure_utc
from app.services.macro_news_snapshot import _row_to_out

logger = logging.getLogger(__name__)

LAST_GOOD_PREFIX = "macro:news:last_good:v1:"
LAST_GOOD_TTL_SEC = 86400 * 14


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def cache_last_good_rows(category: str, rows: list[dict], *, updated_at_iso: str | None) -> None:
    """Persist last good snapshot rows (dicts compatible with _row_to_out) for cold-start fallback."""
    cat = category.lower().strip()
    if not cat or not rows:
        return
    try:
        envelope = {"updated_at": updated_at_iso, "rows": rows[:120]}
        _r().setex(LAST_GOOD_PREFIX + cat, LAST_GOOD_TTL_SEC, json.dumps(envelope))
    except Exception as e:
        logger.debug("macro_news_fallback cache_last_good failed: %s", e)


def cache_last_good_from_items(category: str, items: list[MacroNewsItemOut], *, updated_at_iso: str | None) -> None:
    rows: list[dict] = []
    for it in items[:120]:
        rows.append(
            {
                "id": it.id,
                "title": it.title,
                "source": it.source,
                "timestamp": it.timestamp.isoformat() if hasattr(it.timestamp, "isoformat") else str(it.timestamp),
                "url": it.url,
                "category": it.category,
                "subcategory": it.subcategory,
                "summary": it.summary,
                "sentiment": it.sentiment,
                "impact": it.impact,
                "publisher_tier": it.publisher_tier,
                "publisher_normalized": it.publisher_normalized,
                "duplicate_count": it.duplicate_count,
                "related_publishers": list(it.related_publishers or []),
            }
        )
    cache_last_good_rows(category, rows, updated_at_iso=updated_at_iso)


def load_last_good(category: str) -> tuple[list[MacroNewsItemOut], str | None] | None:
    """Returns (items, updated_at_iso) or None."""
    cat = category.lower().strip()
    try:
        raw = _r().get(LAST_GOOD_PREFIX + cat)
        if not raw:
            return None
        env = json.loads(raw)
        rows = env.get("rows") if isinstance(env, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        updated = env.get("updated_at") if isinstance(env, dict) else None
        outs: list[MacroNewsItemOut] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            o = _row_to_out(r, category_fallback=cat)
            if o:
                outs.append(o)
        if not outs:
            return None
        return outs, str(updated) if updated else None
    except Exception as e:
        logger.debug("macro_news_fallback load_last_good failed: %s", e)
        return None


def _seed_row(
    cat: str,
    *,
    sub: str,
    title: str,
    source: str,
    story_id: str,
) -> MacroNewsItemOut:
    now = datetime.now(timezone.utc)
    return MacroNewsItemOut(
        id=f"demo-{cat}-{story_id}",
        title=title,
        source=source,
        timestamp=ensure_utc(now),
        url=None,
        category=cat,
        subcategory=sub,
        summary=None,
        sentiment="neutral",
        impact=None,
        publisher_tier=3,
        publisher_normalized=None,
        duplicate_count=1,
        related_publishers=[],
    )


def seed_demo_items(category: str, limit: int) -> list[MacroNewsItemOut]:
    """Deterministic placeholder headlines for first paint (not live news)."""
    cat = category.lower().strip()
    templates: dict[str, list[tuple[str, str, str, str]]] = {
        "general": [
            ("General", "g1", "Markets await next policy signals", "NIA Demo"),
            ("Rates", "g2", "Yield curve watched after data prints", "NIA Demo"),
            ("AI", "g3", "Enterprise AI spending stays in focus", "NIA Demo"),
            ("Inflation", "g4", "CPI components tracked across regions", "NIA Demo"),
        ],
        "stock": [
            ("Semiconductors", "s1", "Chip demand indicators mixed by segment", "NIA Demo"),
            ("Software", "s2", "Cloud consumption metrics guide revisions", "NIA Demo"),
            ("Banks", "s3", "Net interest trends under scrutiny", "NIA Demo"),
        ],
        "futures": [
            ("Energy", "f1", "Crude inventory expectations in focus", "NIA Demo"),
            ("Precious Metals", "f2", "Gold range trade near key levels", "NIA Demo"),
        ],
        "crypto": [
            ("BTC", "c1", "Liquidity and flows dominate short-term tape", "NIA Demo"),
            ("ETH", "c2", "Network activity metrics diverge by layer", "NIA Demo"),
        ],
    }
    rows = templates.get(cat, templates["general"])
    out = [_seed_row(cat, sub=a[0], title=a[2], source=a[3], story_id=a[1]) for a in rows]
    return out[: max(1, min(limit, len(out)))]


def resolve_macro_news_fallback(
    category: str,
    subcategory: str | None,
    limit: int,
) -> tuple[list[MacroNewsItemOut], str | None, str, str, str | None]:
    """
    When DB snapshot is missing: Redis last-good, else seed demo.
    Returns (items, data_updated_at_iso, data_source, loading_state, message).
    """
    cat = category.lower().strip()
    lim = max(1, min(limit, 200))
    lg = load_last_good(cat)
    if lg:
        items, lu = lg
        if subcategory:
            sub = subcategory.strip()
            items = [x for x in items if x.subcategory == sub]
        items = items[:lim]
        if items:
            return items, lu, "stale_fallback", "stale", None
    items = seed_demo_items(cat, lim)
    msg: str | None = None
    if subcategory:
        sub = subcategory.strip()
        filtered = [x for x in items if x.subcategory == sub]
        if filtered:
            items = filtered[:lim]
        else:
            items = seed_demo_items(cat, lim)
            msg = f"No snapshot for “{sub}” yet; showing category-level placeholders while data loads."
    else:
        items = items[:lim]
    hint = "Demo headlines only; live macro news is still warming up."
    return items, None, "placeholder", "placeholder", msg or hint
