from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Protocol

import httpx


@dataclass(frozen=True)
class OhlcvBar:
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float


class MarketDataProvider(Protocol):
    name: str

    def ohlcv(self, *, symbol: str) -> list[OhlcvBar]: ...


class StooqProvider:
    """
    Free, no-key daily OHLCV.

    Symbol format:
    - US equities often use e.g. nvda.us
    """

    name = "stooq"

    def ohlcv(self, *, symbol: str) -> list[OhlcvBar]:
        s = symbol.strip().lower()
        if "." not in s:
            s = f"{s}.us"
        url = "https://stooq.com/q/d/l/"
        params = {"s": s, "i": "d"}
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            text = r.text

        # date,open,high,low,close,volume
        reader = csv.DictReader(StringIO(text))
        out: list[OhlcvBar] = []
        for row in reader:
            if not row.get("Date"):
                continue
            dt = datetime.fromisoformat(row["Date"]).replace(tzinfo=timezone.utc)
            try:
                out.append(
                    OhlcvBar(
                        t=dt,
                        o=float(row["Open"]),
                        h=float(row["High"]),
                        l=float(row["Low"]),
                        c=float(row["Close"]),
                        v=float(row.get("Volume") or 0),
                    )
                )
            except ValueError:
                continue
        return out


def get_market_provider(name: str | None) -> MarketDataProvider:
    if not name or name == "stooq":
        return StooqProvider()
    # Future: twelvedata/polygon/alphavantage
    return StooqProvider()

