"""Shared index watchlist defaults (used by API routes + worker)."""

from __future__ import annotations

# Minimal shared universe for V1 snapshot/cache (quotes + OHLCV refresh). Yahoo symbols.
CORE_SHARED_MARKET_SYMBOLS_V1: frozenset[str] = frozenset(
    {
        "^GSPC",  # S&P 500
        "^IXIC",  # NASDAQ Composite
        "^VIX",
        "CL=F",
        "GC=F",
        "BTC-USD",
        "ETH-USD",
    }
)

# Default indices per category (name + symbol only). Built-in categories only.
DEFAULT_INDICES_BY_CATEGORY: dict[str, list[dict]] = {
    "general": [
        {"name": "S&P 500", "symbol": "^GSPC"},
        {"name": "NASDAQ", "symbol": "^IXIC"},
        {"name": "DXY", "symbol": "DX-Y.NYB"},
        {"name": "Oil", "symbol": "CL=F"},
        {"name": "Gold", "symbol": "GC=F"},
        {"name": "VIX", "symbol": "^VIX"},
    ],
    "stock": [
        {"name": "S&P 500", "symbol": "^GSPC"},
        {"name": "NASDAQ", "symbol": "^IXIC"},
        {"name": "Russell 2000", "symbol": "^RUT"},
        {"name": "SOXX", "symbol": "SOXX"},
        {"name": "VIX", "symbol": "^VIX"},
    ],
    "crypto": [
        {"name": "BTC", "symbol": "BTC-USD"},
        {"name": "ETH", "symbol": "ETH-USD"},
    ],
    "futures": [],
}

MAX_INDICES_PER_CATEGORY = 10


def all_default_symbols() -> set[str]:
    """Symbols referenced by built-in category defaults (for scheduled refresh)."""
    out: set[str] = set()
    for _cat, items in DEFAULT_INDICES_BY_CATEGORY.items():
        for it in items:
            sym = (it.get("symbol") or "").strip().upper()
            if sym:
                out.add(sym)
    return out


def core_and_default_symbols() -> set[str]:
    """Union of V1 core names + default watchlist symbols (always refreshed on schedule)."""
    return set(CORE_SHARED_MARKET_SYMBOLS_V1) | all_default_symbols()
