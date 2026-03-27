"""Google Trends via pytrends: daily relative index 0–100 (not absolute volume)."""

from __future__ import annotations

import logging
import random
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


def get_daily_search_trend(terms: list[str], timeframe: str) -> list[dict[str, Any]]:
    """
    Fetch daily Google Trends interest (0–100) for up to 5 terms in one request.
    Multiple terms are combined by **mean** per day.

    Always returns a list (possibly empty). Never raises. Never returns None.
    """
    cleaned = [t.strip() for t in (terms or []) if t and str(t).strip()]
    if not cleaned:
        logger.warning("pytrends returned empty or failed for terms: %s", terms)
        return []

    try:
        tf = normalize_trends_timeframe(timeframe)
        kw_list = cleaned[:5]

        from pytrends.request import TrendReq

        proxies: dict[str, str] | None = None
        if settings.trends_proxy_url:
            u = settings.trends_proxy_url.strip()
            proxies = {"http": u, "https": u}

        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25), proxies=proxies, retries=1, backoff_factor=0.2)
        pytrends.build_payload(kw_list, cat=0, timeframe=tf, geo="", gprop="")
        bump_external("google_trends", 1)
        df = pytrends.interest_over_time()

        _sleep_rate_limit()

        if df is None:
            logger.warning("pytrends returned empty or failed for terms: %s", kw_list)
            return []

        try:
            is_empty = bool(df.empty)
        except Exception:
            is_empty = True
        if is_empty:
            logger.warning("pytrends returned empty or failed for terms: %s", kw_list)
            return []

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

        present_kw = [k for k in kw_list if k in cols]
        if not present_kw:
            logger.warning("pytrends returned empty or failed for terms: %s (missing keyword columns)", kw_list)
            return []

        out: list[dict[str, Any]] = []
        try:
            index_iter = list(df.index)
        except Exception:
            logger.warning("pytrends returned empty or failed for terms: %s", kw_list)
            return []

        for idx in index_iter:
            vals: list[float] = []
            for k in present_kw:
                try:
                    if k not in df.columns:
                        continue
                    cell = df.loc[idx, k]
                    vals.append(float(cell))
                except Exception:
                    continue
            if not vals:
                continue
            combined = sum(vals) / len(vals)
            combined = max(0.0, min(100.0, round(combined, 4)))
            if hasattr(idx, "strftime"):
                ds = idx.strftime("%Y-%m-%d")
            else:
                ds = str(idx)[:10]
            out.append({"date": ds, "search_trend": combined})

        if not out:
            logger.warning("pytrends returned empty or failed for terms: %s", kw_list)
            return []
        return out
    except Exception as e:
        logger.warning("pytrends returned empty or failed for terms: %s (%s)", cleaned, e)
        try:
            _sleep_rate_limit()
        except Exception:
            pass
        return []
