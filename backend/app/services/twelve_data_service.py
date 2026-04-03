"""Twelve Data API client with Redis caching (aligned with existing redis_url)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

TWELVE_BASE = "https://api.twelvedata.com"

# Cache TTLs (seconds)
SEARCH_TTL_SEC = 86400  # 24h
QUOTE_TTL_SEC = 480  # 8 min (within 5-10)
TS_TTL_SEC = 900  # 15 min

SEARCH_KEY_PREFIX = "twelve:v1:search:"
QUOTE_KEY_PREFIX = "twelve:v1:quote:"
TS_KEY_PREFIX = "twelve:v1:ts:"


def _r() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _api_key() -> str | None:
    k = getattr(settings, "twelve_api_key", None)
    if k is None:
        return None
    s = str(k).strip()
    return s or None


def is_twelve_configured() -> bool:
    return _api_key() is not None


def _twelve_request(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    key = _api_key()
    if not key:
        logger.info("external_api:twelve_data:call skipped (no TWELVE_API_KEY) path=%s", path)
        return None
    q = {**params, "apikey": key}
    url = f"{TWELVE_BASE}/{path.lstrip('/')}"
    logger.info("external_api:twelve_data:call path=%s params=%s", path, {k: v for k, v in q.items() if k != "apikey"})
    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.get(url, params=q)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("external_api:twelve_data:error path=%s err=%s", path, e)
        return None
    if isinstance(data, dict) and data.get("status") == "error":
        logger.warning("external_api:twelve_data:error path=%s body=%s", path, str(data)[:500])
        return None
    return data if isinstance(data, dict) else None


def search_symbol(query: str) -> list[dict[str, Any]]:
    """
    GET /symbol_search?symbol={query}
    Returns [{ symbol, name, exchange, type }]
    """
    q = (query or "").strip()
    if not q:
        return []
    cache_k = SEARCH_KEY_PREFIX + hashlib.sha256(q.lower().encode()).hexdigest()
    try:
        raw = _r().get(cache_k)
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    data = _twelve_request("symbol_search", {"symbol": q})
    out: list[dict[str, Any]] = []
    if data:
        rows = data.get("data") or data.get("symbols") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = row.get("symbol") or row.get("ticker")
                if not sym:
                    continue
                name = row.get("instrument_name") or row.get("name") or sym
                exchange = row.get("exchange") or row.get("mic_code") or ""
                typ = row.get("instrument_type") or row.get("type") or ""
                out.append(
                    {
                        "symbol": str(sym).strip().upper(),
                        "name": str(name).strip(),
                        "exchange": str(exchange).strip() if exchange else "",
                        "type": str(typ).strip() if typ else "",
                    }
                )

    if data is not None:
        try:
            _r().setex(cache_k, SEARCH_TTL_SEC, json.dumps(out))
        except Exception:
            pass
    return out


def get_quote(symbol: str) -> dict[str, Any] | None:
    """
    GET /quote?symbol={symbol}
    Returns { symbol, price, change, percent_change, timestamp } or None
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    cache_k = QUOTE_KEY_PREFIX + sym
    try:
        raw = _r().get(cache_k)
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    data = _twelve_request("quote", {"symbol": sym})
    if not data:
        return None

    def _f(x: Any) -> float | None:
        if x is None:
            return None
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    price = _f(data.get("close")) or _f(data.get("price"))
    if price is None:
        return None
    chg = _f(data.get("change"))
    pct = _f(data.get("percent_change"))
    ts_raw = data.get("datetime") or data.get("timestamp") or data.get("last_quote_time")
    if ts_raw:
        ts = str(ts_raw).strip()
    else:
        ts = datetime.now(timezone.utc).isoformat()
    out = {
        "symbol": sym,
        "price": price,
        "change": chg if chg is not None else 0.0,
        "percent_change": pct if pct is not None else 0.0,
        "timestamp": ts,
    }
    if data is not None:
        try:
            _r().setex(cache_k, QUOTE_TTL_SEC, json.dumps(out))
        except Exception:
            pass
    return out


def get_quotes_batch(symbols: list[str]) -> dict[str, dict[str, Any] | None]:
    """
    GET /quote?symbol=AAPL,MSFT,...
    Returns per-symbol dict or None (best-effort).
    """
    syms = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]
    if not syms:
        return {}
    uniq: list[str] = []
    seen: set[str] = set()
    for s in syms:
        if s not in seen:
            seen.add(s)
            uniq.append(s)

    # Twelve supports comma-separated symbols for quote; response may be { symbol: {...} } OR list-like.
    data = _twelve_request("quote", {"symbol": ",".join(uniq)})
    out: dict[str, dict[str, Any] | None] = {s: None for s in uniq}
    if not data:
        return out

    def _coerce_quote(sym: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        def _f(x: Any) -> float | None:
            if x is None:
                return None
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        price = _f(payload.get("close")) or _f(payload.get("price"))
        if price is None:
            return None
        chg = _f(payload.get("change"))
        pct = _f(payload.get("percent_change"))
        ts_raw = payload.get("datetime") or payload.get("timestamp") or payload.get("last_quote_time")
        ts = str(ts_raw).strip() if ts_raw else datetime.now(timezone.utc).isoformat()
        return {
            "symbol": sym,
            "price": price,
            "change": chg if chg is not None else 0.0,
            "percent_change": pct if pct is not None else 0.0,
            "timestamp": ts,
        }

    if "symbol" in data and data.get("close") is not None:
        sym = str(data.get("symbol") or "").strip().upper()
        if sym:
            out[sym] = _coerce_quote(sym, data)
        return out

    # Some plans respond: { "AAPL": {...}, "MSFT": {...} }
    for sym, payload in data.items():
        if not isinstance(payload, dict):
            continue
        s = str(sym).strip().upper()
        if s in out:
            out[s] = _coerce_quote(s, payload)

    # Cache best-effort per symbol (keep same TTL as single quote).
    try:
        r = _r()
        for s, q in out.items():
            if q and isinstance(q, dict) and q.get("price") is not None:
                r.setex(QUOTE_KEY_PREFIX + s, QUOTE_TTL_SEC, json.dumps(q))
    except Exception:
        pass
    return out


def get_time_series(symbol: str, interval: str = "1day", outputsize: int = 100) -> list[dict[str, Any]]:
    """
    GET /time_series?symbol=&interval=&outputsize=
    Returns [{ time: ISO string, open, high, low, close, volume }]
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    iv = (interval or "1day").strip() or "1day"
    osz = max(1, min(int(outputsize), 5000))
    cache_k = f"{TS_KEY_PREFIX}{sym}:{iv}:{osz}"
    try:
        raw = _r().get(cache_k)
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    data = _twelve_request("time_series", {"symbol": sym, "interval": iv, "outputsize": str(osz)})
    out: list[dict[str, Any]] = []
    if data:
        rows = data.get("values") or data.get("data") or []
        if isinstance(rows, list):
            # Twelve returns newest first; reverse to ascending time for charts
            rows_iter = list(reversed(rows))
            for row in rows_iter:
                if not isinstance(row, dict):
                    continue
                dt = row.get("datetime") or row.get("date") or row.get("time")
                if not dt:
                    continue
                t_iso = str(dt).strip()
                if len(t_iso) == 10 and t_iso.count("-") == 2:
                    t_iso = f"{t_iso}T00:00:00+00:00"

                def _fv(k: str) -> float:
                    v = row.get(k)
                    if v is None:
                        return 0.0
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return 0.0

                out.append(
                    {
                        "time": t_iso,
                        "open": _fv("open"),
                        "high": _fv("high"),
                        "low": _fv("low"),
                        "close": _fv("close"),
                        "volume": _fv("volume"),
                    }
                )

    if data is not None:
        try:
            _r().setex(cache_k, TS_TTL_SEC, json.dumps(out))
        except Exception:
            pass
    return out


def get_time_series_batch(
    symbols: list[str],
    *,
    interval: str = "1day",
    outputsize: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    """
    Batch-shaped adapter for Twelve time_series.

    Twelve REST time_series is per-symbol in our current client, so this function loops
    within the chunk. Business layers should still treat this as a batch interface.
    """
    syms = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]
    uniq: list[str] = []
    seen: set[str] = set()
    for s in syms:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in uniq}
    if not uniq:
        return out
    for s in uniq:
        try:
            out[s] = get_time_series(s, interval=interval, outputsize=outputsize) or []
        except Exception:
            out[s] = []
    return out
