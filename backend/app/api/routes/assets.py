from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

# Example symbols for search; can be replaced with DB or external API later.
EXAMPLE_SYMBOLS = [
    # Equities / ETFs
    {"symbol": "NVDA", "name": "NVIDIA Corporation"},
    {"symbol": "SOXX", "name": "iShares Semiconductor ETF"},
    {"symbol": "SMH", "name": "VanEck Semiconductor ETF"},
    {"symbol": "AMD", "name": "Advanced Micro Devices"},
    {"symbol": "TSM", "name": "Taiwan Semiconductor"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust"},
    {"symbol": "AAPL", "name": "Apple Inc."},
    {"symbol": "MSFT", "name": "Microsoft Corporation"},
    {"symbol": "GOOGL", "name": "Alphabet Inc."},
    {"symbol": "META", "name": "Meta Platforms"},
    {"symbol": "AMZN", "name": "Amazon.com Inc."},
    # Crypto
    {"symbol": "BTC", "name": "Bitcoin"},
    {"symbol": "ETH", "name": "Ethereum"},
    # Forex
    {"symbol": "EURUSD", "name": "Euro / US Dollar"},
    # Futures
    {"symbol": "CL", "name": "Crude Oil Futures"},
    # Gold / precious metals
    {"symbol": "XAUUSD", "name": "Gold Spot"},
    {"symbol": "GLD", "name": "SPDR Gold Shares"},
]


@router.get("/search")
def search_assets(
    q: str = Query(..., min_length=1, max_length=30),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Search asset symbols. Returns matches by symbol or name (case-insensitive)."""
    q_lower = q.strip().upper() if q else ""
    if not q_lower:
        return []
    results = []
    for item in EXAMPLE_SYMBOLS:
        if q_lower in item["symbol"].upper() or (item.get("name") and q_lower in item["name"].upper()):
            results.append(item)
    return results[:20]
