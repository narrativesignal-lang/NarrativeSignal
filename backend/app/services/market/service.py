from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

from app.services.market.providers import OhlcvBar, get_market_provider
from app.services.market_indices_config import core_and_default_symbols

logger = logging.getLogger(__name__)

# Symbols used for extra logging when Yahoo/Stooq returns empty (aligned with scheduled refresh universe).
DEFAULT_INDEX_SYMBOLS = frozenset(core_and_default_symbols())


def fetch_quote(symbol: str) -> dict:
    """
    Fetch last price and daily change for a symbol.
    Method 1: yf.download (most reliable in Docker).
    Method 2: ticker.history fallback.
    Returns {"price": float|None, "change_percent": float|None}; None when no data.
    """
    price: float | None = None
    prev_close: float | None = None

    # Method 1: yf.download (most reliable in Docker)
    try:
        df = yf.download(
            symbol, period="5d", interval="1d", progress=False, auto_adjust=False, threads=False
        )
        if df is not None and not df.empty:
            # Flatten MultiIndex columns when downloading a single symbol
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
        logger.debug("fetch_quote download failed for %s: %s", symbol, e)

    # Method 2: ticker.history fallback
    if price is None or prev_close is None:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
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
            logger.debug("fetch_quote history failed for %s: %s", symbol, e)

    if price is None or prev_close in (None, 0):
        if symbol in DEFAULT_INDEX_SYMBOLS:
            logger.warning("Market index quote failed for symbol: %s (price=%s, prev_close=%s)", symbol, price, prev_close)
        return {"price": None, "change_percent": None}

    change_percent = ((price - prev_close) / prev_close) * 100
    return {"price": price, "change_percent": change_percent}


PERIOD_TO_DAYS: dict[str, int | None] = {
    "1D": 7,  # daily bars; return last ~week so chart isn't empty
    "5D": 10,
    "1M": 35,
    "6M": 200,
    "1Y": 400,
    "MAX": None,
}


def get_ohlcv(*, symbol: str, period: str = "1M", provider_name: str | None = None) -> list[OhlcvBar]:
    p = period.upper()
    days = PERIOD_TO_DAYS.get(p, 35)
    bars: list[OhlcvBar] = []

    # 1) Try Stooq
    try:
        provider = get_market_provider(provider_name)
        bars = provider.ohlcv(symbol=symbol)
    except Exception as e:
        logger.debug("Stooq ohlcv failed for %s: %s", symbol, e)

    # 2) Fallback: yfinance (same as fetch_quote)
    if not bars:
        try:
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
        except Exception as e:
            logger.debug("yfinance ohlcv fallback failed for %s: %s", symbol, e)

    if not bars:
        return []
    if days is None:
        return bars
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [b for b in bars if b.t >= cutoff]

