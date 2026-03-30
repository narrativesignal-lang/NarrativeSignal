"""
Normalize symbols for internal use and map to Twelve Data tickers (v1: pattern + blocklist only).

Does not auto-fix HK/A-share/commodity notation — unmapped symbols return None → direct fallback.
"""

from __future__ import annotations

import re

# US equities / ETFs: simple 1–5 letter tickers (covers AAPL, SPY, QQQ, MSFT, …).
_TWELVE_US_TICKER = re.compile(r"^[A-Z]{1,5}$")
# Crypto spot-style pairs: BTC/USD, ETH/USD, ETH/USDT, …
_TWELVE_CRYPTO_PAIR = re.compile(r"^[A-Z][A-Z0-9]{1,9}/[A-Z]{2,10}$")

_UNSUPPORTED_EXCH_SUFFIX = (".HK", ".SH", ".SZ")
_UNSUPPORTED_METAL_PAIRS = frozenset({"XAU/USD", "XAG/USD"})
_FUTURES_ROOT_BLOCKLIST = frozenset({"CL", "GC", "ES", "NQ"})


def normalize_user_symbol(symbol: str) -> str:
    """Strip, uppercase; slash pairs (e.g. BTC/USD) stay as BASE/QUOTE after upper."""
    return (symbol or "").strip().upper()


def map_symbol_for_twelve(symbol: str) -> str | None:
    """
    If the normalized form is supported for Twelve primary, return the Twelve symbol string.
    Otherwise None → callers should skip Twelve and use fallback only.

    Expects typical callers to pass output of normalize_user_symbol (idempotent).
    """
    s = normalize_user_symbol(symbol)
    if not s:
        return None
    for suf in _UNSUPPORTED_EXCH_SUFFIX:
        if suf in s:
            return None
    if s in _UNSUPPORTED_METAL_PAIRS:
        return None
    if "/" in s:
        if _TWELVE_CRYPTO_PAIR.fullmatch(s):
            return s
        return None
    if s in _FUTURES_ROOT_BLOCKLIST:
        return None
    if _TWELVE_US_TICKER.fullmatch(s):
        return s
    return None
