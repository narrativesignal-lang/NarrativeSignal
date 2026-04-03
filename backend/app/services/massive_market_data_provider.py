"""Massive market snapshots: parsing + DB writes. All HTTP goes through ``massive_api_client`` only."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.data_subscription import MarketQuoteSnapshot, OhlcvSnapshot
from app.services.cache_fallback import merge_quote_row, utcnow
from app.services.massive_api_client import massive_http_aggs_range, massive_http_unified_snapshot

logger = logging.getLogger(__name__)

_PROVIDER_SOURCE = "massive_repair"


@dataclass(frozen=True)
class MassiveBatchResult:
    quotes: dict[str, dict[str, Any] | None]
    ohlcv: dict[str, list[dict[str, Any]]]


def massive_enabled() -> bool:
    key = getattr(settings, "massive_api_key", None)
    return bool(str(key).strip()) if key is not None else False


def _norm_symbols(symbols: list[str]) -> list[str]:
    return [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]


def massive_ticker_for_symbol(symbol: str) -> str:
    """Map user/instrument symbol to Massive ticker segment (also used by repair scan)."""
    s = (symbol or "").strip().upper()
    if not s:
        return s
    if s.startswith(("X:", "I:", "O:", "C:", "F:")):
        return s
    if "/" in s:
        a, b = (p.strip().upper() for p in s.split("/", 1))
        if a and b:
            return f"X:{a}{b}"
    if "-" in s:
        a, b = (p.strip().upper() for p in s.split("-", 1))
        if a and b and len(a) <= 6 and len(b) <= 6:
            return f"X:{a}{b}"
    return s


def _to_iso_from_ns(ns: int | float | None) -> str | None:
    try:
        if ns is None:
            return None
        sec = float(ns) / 1_000_000_000.0
        return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _parse_snapshot_to_quote(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    if row.get("error"):
        return None

    session = row.get("session") if isinstance(row.get("session"), dict) else {}
    price = session.get("close")
    if price is None:
        lt = row.get("last_trade") if isinstance(row.get("last_trade"), dict) else {}
        price = lt.get("price")
    if price is None:
        price = row.get("value")

    if price is None:
        return None

    chg_pct = session.get("change_percent")
    try:
        chg_pct = float(chg_pct) if chg_pct is not None else None
    except Exception:
        chg_pct = None

    return {
        "price": float(price),
        "change_percent": chg_pct,
        "last_updated": _to_iso_from_ns(row.get("last_updated")),
        "type": row.get("type"),
        "timeframe": row.get("timeframe"),
    }


def fetch_massive_quotes_batch(symbols: list[str]) -> tuple[dict[str, dict[str, Any] | None], str | None]:
    """
    One Massive HTTP request via ``massive_api_client`` (quota enforced there).

    Returns ``(quote_map, stop_reason)``. ``stop_reason`` is set when the job must stop
    (quota, 429, HTTP error) — not when Massive simply returned no rows.
    """
    syms = _norm_symbols(symbols)
    if not massive_enabled():
        return {s: None for s in syms}, None
    if not syms:
        return {}, None

    tickers = {massive_ticker_for_symbol(s): s for s in syms}
    outcome = massive_http_unified_snapshot(
        ticker_any_of=",".join(tickers.keys()),
        limit=min(250, len(tickers)),
        log_context="fetch_massive_quotes_batch",
    )
    if outcome.quota_reason:
        logger.info(
            "job=massive_provider fetch_massive_quotes_batch stopped=1 reason=%s symbol_count=%s",
            outcome.quota_reason,
            len(syms),
        )
        return {s: None for s in syms}, outcome.quota_reason
    if outcome.rate_limited:
        return {s: None for s in syms}, "massive_rate_limited"
    if outcome.http_error or not isinstance(outcome.payload, dict):
        return {s: None for s in syms}, None

    payload = outcome.payload
    results = payload.get("results")
    out: dict[str, dict[str, Any] | None] = {s: None for s in syms}
    if not isinstance(results, list):
        return out, None

    for row in results:
        if not isinstance(row, dict):
            continue
        t = (row.get("ticker") or "").strip().upper()
        if not t:
            continue
        src_sym = tickers.get(t)
        if not src_sym:
            continue
        out[src_sym] = _parse_snapshot_to_quote(row)
    return out, None


def _bars_from_aggs_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    bars: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        if row.get("t") is None:
            continue
        bars.append(
            {
                "t": int(row["t"]),
                "o": row.get("o"),
                "h": row.get("h"),
                "l": row.get("l"),
                "c": row.get("c"),
                "v": row.get("v"),
                "n": row.get("n"),
                "vw": row.get("vw"),
            }
        )
    return bars


def _period_to_range(period: str) -> tuple[str, str, str]:
    p = (period or "1M").strip().upper()
    days = 30
    timespan = "day"
    if p in {"1W"}:
        days = 7
    elif p in {"3M"}:
        days = 90
    elif p in {"6M"}:
        days = 180
    elif p in {"1Y", "12M"}:
        days = 365
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    return (from_d.isoformat(), to_d.isoformat(), timespan)


def fetch_massive_ohlcv_batch(
    symbols: list[str], *, period: str = "1M"
) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    """
    One Massive HTTP request per symbol; quota enforced inside ``massive_api_client`` per call.
    Stops immediately on quota or 429 (returns partial map + stop_reason). No retries.
    """
    syms = _norm_symbols(symbols)
    if not massive_enabled():
        return {s: [] for s in syms}, None
    if not syms:
        return {}, None

    from_d, to_d, timespan = _period_to_range(period)
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in syms}
    stop: str | None = None
    for s in syms:
        mt = massive_ticker_for_symbol(s)
        outcome = massive_http_aggs_range(
            massive_ticker=mt,
            from_date=from_d,
            to_date=to_d,
            timespan=timespan,
            log_context=f"fetch_massive_ohlcv_batch:{s}",
        )
        if outcome.quota_reason:
            logger.info(
                "job=massive_provider fetch_massive_ohlcv_batch stopped=1 reason=%s symbol=%s",
                outcome.quota_reason,
                s,
            )
            stop = outcome.quota_reason
            break
        if outcome.rate_limited:
            stop = "massive_rate_limited"
            break
        if outcome.http_error:
            logger.warning("job=massive_provider ohlcv http_error symbol=%s", s)
            continue
        out[s] = _bars_from_aggs_payload(outcome.payload if isinstance(outcome.payload, dict) else None)
    return out, stop


def write_massive_quotes_to_snapshots(db: Session, qmap: dict[str, dict[str, Any] | None]) -> int:
    attempt = utcnow()
    wrote = 0
    for sym, qr in (qmap or {}).items():
        s = (sym or "").strip().upper()
        if not s:
            continue
        snap = db.get(MarketQuoteSnapshot, s)
        if snap is None:
            snap = MarketQuoteSnapshot(symbol=s)
            db.add(snap)

        snap.last_attempt_at = attempt
        if not qr or qr.get("price") is None:
            snap.last_error = snap.last_error or "massive_no_data"
            snap.is_stale = True
            continue

        new_price = float(qr["price"])
        new_change = qr.get("change_percent")
        try:
            new_change = float(new_change) if new_change is not None else None
        except Exception:
            new_change = None

        snap.price, snap.change_percent = merge_quote_row(snap.price, snap.change_percent, new_price, new_change)
        snap.provider_source = _PROVIDER_SOURCE
        snap.last_success_at = attempt
        snap.last_error = None
        snap.is_stale = False
        snap.extra = {
            "massive": {
                "last_updated": qr.get("last_updated"),
                "type": qr.get("type"),
                "timeframe": qr.get("timeframe"),
            }
        }
        wrote += 1
    return wrote


def write_massive_ohlcv_to_snapshots(db: Session, omap: dict[str, list[dict[str, Any]]], *, period: str) -> int:
    attempt = utcnow()
    wrote = 0
    p = (period or "1M").strip().upper()
    for sym, bars in (omap or {}).items():
        s = (sym or "").strip().upper()
        if not s:
            continue
        key = f"{s}:{p}"
        snap = db.get(OhlcvSnapshot, key)
        if snap is None:
            snap = OhlcvSnapshot(snapshot_key=key, symbol=s, period=p)
            db.add(snap)

        snap.last_attempt_at = attempt
        if not bars:
            snap.last_error = snap.last_error or "massive_no_data"
            snap.is_stale = True
            continue

        out_bars: list[dict[str, Any]] = []
        for b in bars:
            if not isinstance(b, dict):
                continue
            if b.get("t") is None:
                continue
            out_bars.append(
                {
                    "t": int(b["t"]),
                    "o": b.get("o"),
                    "h": b.get("h"),
                    "l": b.get("l"),
                    "c": b.get("c"),
                    "v": b.get("v"),
                }
            )

        if not out_bars:
            snap.last_error = snap.last_error or "massive_no_data"
            snap.is_stale = True
            continue

        snap.bars = {"bars": out_bars}
        snap.provider_source = _PROVIDER_SOURCE
        snap.last_success_at = attempt
        snap.last_error = None
        snap.is_stale = False
        wrote += 1
    return wrote
