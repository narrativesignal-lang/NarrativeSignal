from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

from app.services.external_api_stats import bump as bump_external
from app.services.market.yahoo_guard import (
    exception_looks_like_yahoo_rate_limit,
    yahoo_mark_rate_limited,
    yahoo_provider_paused,
    yahoo_spacing_sleep_before_call,
)
from app.services.market.providers import OhlcvBar, get_market_provider
from app.services.market_indices_config import core_and_default_symbols

logger = logging.getLogger(__name__)

# Symbols used for extra logging when Yahoo/Stooq returns empty (aligned with scheduled refresh universe).
DEFAULT_INDEX_SYMBOLS = frozenset(core_and_default_symbols())


def fetch_quote_stooq(symbol: str) -> dict:
    """
    Stooq daily OHLCV → latest close vs prior close (no Yahoo).

    Returns {"price": float|None, "change_percent": float|None, "_stooq_used": bool}.
    """
    try:
        provider = get_market_provider("stooq")
        bars = provider.ohlcv(symbol=symbol)
        if not bars:
            return {"price": None, "change_percent": None, "_stooq_used": True}
        last = bars[-1]
        price = float(last.c)
        change_percent: float | None = None
        if len(bars) >= 2:
            prev_close = float(bars[-2].c)
            if prev_close not in (0.0,):
                change_percent = ((price - prev_close) / prev_close) * 100
        bump_external("stooq_quote", 1)
        return {"price": price, "change_percent": change_percent, "_stooq_used": True}
    except Exception as e:
        logger.debug("fetch_quote_stooq failed for %s: %s", symbol, e)
        return {"price": None, "change_percent": None, "_stooq_used": True}


def fetch_quote_yahoo(symbol: str) -> dict:
    """
    Yahoo/yfinance quote (LAST fallback — Twelve/Stooq are handled in market_snapshots / fetch_quote_stooq).

    Returns {"price": float|None, "change_percent": float|None, "_yahoo_used": bool}.
    Respects Redis pause after rate limits; spaces consecutive calls.
    """
    price: float | None = None
    prev_close: float | None = None
    yahoo_used = False

    if yahoo_provider_paused():
        logger.info(
            "market_pipeline symbol=%s yahoo_skipped_due_to_cooldown reason=provider_paused",
            symbol,
        )
        return {"price": None, "change_percent": None, "_yahoo_used": False}

    yahoo_spacing_sleep_before_call()

    # Method 1: yf.download (most reliable in Docker)
    try:
        df = yf.download(
            symbol, period="5d", interval="1d", progress=False, auto_adjust=False, threads=False
        )
        yahoo_used = True
        if df is not None and not df.empty:
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df = df.copy()
                df.columns = df.columns.get_level_values(0)
            closes = df["Close"].dropna() if "Close" in df.columns else None
            opens = df["Open"].dropna() if "Open" in df.columns else None
            if closes is not None and len(closes) >= 1:
                price = float(closes.iloc[-1])
                if len(closes) >= 2:
                    prev_close = float(closes.iloc[-2])
                elif opens is not None and len(opens) >= 1:
                    prev_close = float(opens.iloc[-1])
    except Exception as e:
        logger.warning("fetch_quote download failed for %s: %s", symbol, e)
        if exception_looks_like_yahoo_rate_limit(e):
            yahoo_mark_rate_limited()
        yahoo_used = True

    # Method 2: ticker.history fallback (single extra yahoo call — spaced already, no second sleep)
    if price is None or prev_close is None:
        try:
            yahoo_spacing_sleep_before_call()
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
            yahoo_used = True
            if hist is not None and not hist.empty:
                closes = hist["Close"].dropna()
                opens = hist["Open"].dropna() if "Open" in hist.columns else None
                if len(closes) >= 1:
                    price = float(closes.iloc[-1])
                    if len(closes) >= 2:
                        prev_close = float(closes.iloc[-2])
                    elif opens is not None and len(opens) >= 1:
                        prev_close = float(opens.iloc[-1])
        except Exception as e:
            logger.warning("fetch_quote history failed for %s: %s", symbol, e)
            if exception_looks_like_yahoo_rate_limit(e):
                yahoo_mark_rate_limited()
            yahoo_used = True

    if price is None or prev_close in (None, 0):
        if symbol in DEFAULT_INDEX_SYMBOLS:
            logger.warning("Market index quote failed for symbol: %s (price=%s, prev_close=%s)", symbol, price, prev_close)
        return {"price": None, "change_percent": None, "_yahoo_used": yahoo_used}

    change_percent = ((price - prev_close) / prev_close) * 100
    bump_external("yahoo_quote", 1)
    return {"price": price, "change_percent": change_percent, "_yahoo_used": yahoo_used}


def fetch_quote(symbol: str) -> dict:
    """
    Stooq then Yahoo (for callers that do not orchestrate Twelve). Does not apply snapshot-aware Yahoo skip.
    """
    s = fetch_quote_stooq(symbol)
    if s.get("price") is not None:
        return {**s, "_yahoo_used": False}
    y = fetch_quote_yahoo(symbol)
    return y


PERIOD_TO_DAYS: dict[str, int | None] = {
    "1D": 7,
    "5D": 10,
    "1M": 35,
    "6M": 200,
    "1Y": 400,
    "MAX": None,
}


def get_ohlcv(*, symbol: str, period: str = "1M", provider_name: str | None = None) -> tuple[list[OhlcvBar], str]:
    """
    OHLCV: Stooq first, then Yahoo. Returns (bars, source_label) where source_label is
    stooq_fallback | yahoo_fallback | empty.
    """
    p = period.upper()
    days = PERIOD_TO_DAYS.get(p, 35)
    bars: list[OhlcvBar] = []

    # 1) Try Stooq
    try:
        provider = get_market_provider(provider_name)
        bars = provider.ohlcv(symbol=symbol)
    except Exception as e:
        logger.debug("Stooq ohlcv failed for %s: %s", symbol, e)

    if bars:
        bump_external("stooq_ohlcv", 1)
        if days is None:
            return bars, "stooq_fallback"
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [b for b in bars if b.t >= cutoff], "stooq_fallback"

    # 2) Fallback: yfinance
    if yahoo_provider_paused():
        logger.info(
            "market_pipeline symbol=%s period=%s yahoo_skipped_due_to_cooldown reason=provider_paused ohlcv=1",
            symbol,
            p,
        )
        return [], "empty"

    try:
        yahoo_spacing_sleep_before_call()
        yf_period = {"1D": "5d", "5D": "1mo", "1M": "3mo", "6M": "6mo", "1Y": "1y", "MAX": "max"}.get(p, "3mo")
        df = yf.download(symbol, period=yf_period, interval="1d", progress=False, auto_adjust=False, threads=False)
        if df is not None and not df.empty:
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df = df.copy()
                df.columns = df.columns.get_level_values(0)
            for idx, row in df.iterrows():
                ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else datetime.fromisoformat(str(idx))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                bars.append(
                    OhlcvBar(
                        t=ts,
                        o=float(row.get("Open", 0)),
                        h=float(row.get("High", 0)),
                        l=float(row.get("Low", 0)),
                        c=float(row.get("Close", 0)),
                        v=float(row.get("Volume", 0)),
                    )
                )
        if bars:
            bump_external("yahoo_ohlcv", 1)
    except Exception as e:
        logger.warning("yfinance ohlcv fallback failed for %s: %s", symbol, e)
        if exception_looks_like_yahoo_rate_limit(e):
            yahoo_mark_rate_limited()

    if not bars:
        return [], "empty"
    if days is None:
        return bars, "yahoo_fallback"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [b for b in bars if b.t >= cutoff], "yahoo_fallback"
