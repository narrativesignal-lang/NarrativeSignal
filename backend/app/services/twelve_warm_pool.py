"""
Fixed warm pool: symbols that use Twelve Data as primary on /api/market/quote and time_series.
Celery tasks refresh Redis (via twelve_data_service) + DB snapshots for faster first paint.
"""

from __future__ import annotations

# Only include symbols validated for Twelve primary (see twelve_symbol_support policy).
TWELVE_WARM_POOL_SYMBOLS: tuple[str, ...] = (
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "SPY",
    "QQQ",
    "BTC/USD",
    "ETH/USD",
)

# Must match market.py PERIOD_TO_TWELVE["1M"] for consistent 1M warm bars.
TWELVE_WARM_1M_INTERVAL: tuple[str, int] = ("1day", 40)


def _assert_warm_pool_symbols_supported() -> None:
    from app.services.market_provider_router import route_quote_provider, route_time_series_provider

    bad = [
        s
        for s in TWELVE_WARM_POOL_SYMBOLS
        if route_quote_provider(s) != "twelvedata" or route_time_series_provider(s) != "twelvedata"
    ]
    if bad:
        raise RuntimeError(f"TWELVE_WARM_POOL_SYMBOLS contains Twelve-unsupported entries: {bad}")


_assert_warm_pool_symbols_supported()
