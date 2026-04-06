"""Google Trends via pytrends: daily relative index 0–100 (not absolute volume)."""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

from app.core.config import settings
from app.services.external_api_stats import bump as bump_external

logger = logging.getLogger(__name__)

_ALLOWED_TIMEFRAMES = frozenset({"now 7-d", "today 3-m", "today 6-m"})


def normalize_trends_timeframe(timeframe: str | None) -> str:
    t = (timeframe or "").strip()
    if t in _ALLOWED_TIMEFRAMES:
        return t
    return settings.trends_default_timeframe if settings.trends_default_timeframe in _ALLOWED_TIMEFRAMES else "today 6-m"


def _sleep_rate_limit() -> None:
    time.sleep(settings.trends_request_sleep_seconds + random.uniform(0, 0.5))


def _is_ticker_like(keyword: str) -> bool:
    s = (keyword or "").strip()
    if not s or " " in s:
        return False
    return bool(re.fullmatch(r"[A-Z0-9.\-]{1,8}", s))


def _candidate_keywords(keyword: str, fallback_keyword: str | None = None) -> list[str]:
    base = (keyword or "").strip()
    if not base:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _push(v: str | None) -> None:
        x = (v or "").strip()
        if not x:
            return
        lk = x.lower()
        if lk in seen:
            return
        seen.add(lk)
        out.append(x)

    _push(base)
    # Ticker-only terms are often unstable in pytrends; "TICKER stock" is typically safer.
    if _is_ticker_like(base.upper()):
        _push(f"{base} stock")
    _push(fallback_keyword)
    return out


def get_daily_interest_single_keyword(
    keyword: str,
    timeframe: str,
    *,
    fallback_keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    One Google Trends request per keyword (no multi-keyword batch used as combined series).
    Returns [{"date": "YYYY-MM-DD", "value": float 0–100}, ...]. Never raises.
    """
    cleaned = (keyword or "").strip()
    if not cleaned:
        return []
    candidates = _candidate_keywords(cleaned, fallback_keyword=fallback_keyword)
    if not candidates:
        return []

    try:
        tf = normalize_trends_timeframe(timeframe)
        from pytrends.request import TrendReq

        proxies: dict[str, str] | None = None
        if settings.trends_proxy_url:
            u = settings.trends_proxy_url.strip()
            proxies = {"http": u, "https": u}

        for term in candidates:
            try:
                pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25), proxies=proxies, retries=1, backoff_factor=0.2)
                pytrends.build_payload([term], cat=0, timeframe=tf, geo="", gprop="")
                bump_external("google_trends", 1)
                df = pytrends.interest_over_time()
                _sleep_rate_limit()
            except Exception as e:
                logger.warning("pytrends failed keyword=%s err=%s", term[:80], str(e)[:200])
                try:
                    _sleep_rate_limit()
                except Exception:
                    pass
                continue

            if df is None:
                logger.info("pytrends empty df keyword=%s", term[:80])
                continue

            try:
                is_empty = bool(df.empty)
            except Exception:
                is_empty = True
            if is_empty:
                logger.info("pytrends empty df keyword=%s", term[:80])
                continue

            try:
                cols = list(df.columns)
            except Exception:
                cols = []
            if "isPartial" in cols:
                try:
                    df = df.drop(columns=["isPartial"])
                    cols = [c for c in cols if c != "isPartial"]
                except Exception:
                    pass

            if term not in cols:
                logger.info("pytrends missing column keyword=%s cols=%s", term[:80], cols[:10])
                continue

            out: list[dict[str, Any]] = []
            try:
                index_iter = list(df.index)
            except Exception:
                continue

            for idx in index_iter:
                try:
                    cell = df.loc[idx, term]
                    val = max(0.0, min(100.0, round(float(cell), 4)))
                except Exception:
                    continue
                if hasattr(idx, "strftime"):
                    ds = idx.strftime("%Y-%m-%d")
                else:
                    ds = str(idx)[:10]
                out.append({"date": ds, "value": val})
            if out:
                return out
        return []
    except Exception as e:
        logger.warning("pytrends failed keyword=%s err=%s", cleaned[:80], str(e)[:200])
        try:
            _sleep_rate_limit()
        except Exception:
            pass
        return []


def get_daily_search_trend(terms: list[str], timeframe: str) -> list[dict[str, Any]]:
    """
    Deprecated for entity metrics: use get_daily_interest_single_keyword per term.
    Kept for compatibility: fetches each term independently and averages per day (not additive).
    """
    cleaned = [t.strip() for t in (terms or []) if t and str(t).strip()]
    if not cleaned:
        return []
    by_date: dict[str, list[float]] = {}
    for term in cleaned[:8]:
        for p in get_daily_interest_single_keyword(term, timeframe):
            ds = str(p.get("date") or "")
            if not ds:
                continue
            by_date.setdefault(ds, []).append(float(p["value"]))
    out: list[dict[str, Any]] = []
    for ds in sorted(by_date.keys()):
        vals = by_date[ds]
        if not vals:
            continue
        combined = sum(vals) / len(vals)
        out.append({"date": ds, "search_trend": max(0.0, min(100.0, round(combined, 4)))})
    return out
