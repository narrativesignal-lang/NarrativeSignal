"""Logical provider routing for quote/time_series with ordered fallback chain."""

from __future__ import annotations

from typing import Literal

from app.services.symbol_mapping import map_symbol_for_twelve, normalize_user_symbol

PRIMARY_PROVIDER = "twelve"
FALLBACK_CHAIN = ["yahoo", "fallback_provider"]

MarketQuoteProvider = Literal["twelve", "yahoo", "fallback_provider", "unavailable"]
MarketTimeSeriesProvider = Literal["twelve", "yahoo", "fallback_provider", "unavailable"]


def _primary_route(symbol: str) -> Literal["twelve", "fallback_provider"]:
    if map_symbol_for_twelve(normalize_user_symbol(symbol)) is not None:
        return "twelve"
    return "fallback_provider"


def route_quote_provider(symbol: str) -> MarketQuoteProvider:
    """Which provider should handle GET /api/market/quote for this symbol (normalized inside)."""
    return _primary_route(symbol)


def route_time_series_provider(symbol: str) -> MarketTimeSeriesProvider:
    """Which provider should handle GET /api/market/time_series for this symbol (normalized inside)."""
    return _primary_route(symbol)
