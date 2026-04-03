"""
Fixed warm pool: symbols that use Twelve Data as primary on /api/market/quote and time_series.
Celery tasks refresh Redis (via twelve_data_service) + DB snapshots for faster first paint.
"""

from __future__ import annotations

# Only include symbols validated for Twelve primary (see twelve_symbol_support policy).
_TWELVE_WARM_POOL_SYMBOLS_CONFIG: tuple[str, ...] = (
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


def _resolve_supported_warm_pool_symbols() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Warm pool must never crash app startup.

    - Filters out unsupported symbols.
    - Logs a warning listing skipped symbols.
    - If nothing is supported, warm pool auto-disables (empty list).
    """
    from app.services.market_provider_router import route_quote_provider, route_time_series_provider

    supported: list[str] = []
    skipped: list[str] = []
    for s in _TWELVE_WARM_POOL_SYMBOLS_CONFIG:
        if route_quote_provider(s) == "twelve" and route_time_series_provider(s) == "twelve":
            supported.append(s)
        else:
            skipped.append(s)
    return tuple(supported), tuple(skipped)


TWELVE_WARM_POOL_SYMBOLS, _TWELVE_WARM_POOL_SKIPPED = _resolve_supported_warm_pool_symbols()

if _TWELVE_WARM_POOL_SKIPPED:
    import logging

    logging.getLogger(__name__).warning(
        "twelve_warm_pool: skipped unsupported symbols: %s",
        list(_TWELVE_WARM_POOL_SKIPPED),
    )

if not TWELVE_WARM_POOL_SYMBOLS:
    import logging

    logging.getLogger(__name__).warning(
        "twelve_warm_pool: disabled (no supported symbols in config)"
    )
