"""Policy: Twelve-eligible symbols (delegates to market provider router)."""

from __future__ import annotations

from app.services.market_provider_router import route_quote_provider


def is_twelve_supported_symbol(symbol: str) -> bool:
    """True if quote route is Twelve primary for this symbol."""
    return route_quote_provider(symbol) == "twelvedata"
