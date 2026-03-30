#!/usr/bin/env python3
"""
Market API + Twelve Data coverage smoke test.

Calls existing endpoints only (no imports of app business logic):
  GET /api/market/search?q=...
  GET /api/market/quote?symbol=...
  GET /api/market/time_series?symbol=...&period=1M

Requires a running backend (default http://127.0.0.1:8000).

Auth for /market/search:
  - NARRATIVE_TEST_TOKEN (Bearer), or
  - NARRATIVE_TEST_EMAIL + NARRATIVE_TEST_PASSWORD (login once)

Otherwise search calls are attempted and failures are reported as unauthenticated.

Usage:
  cd backend
  python scripts/test_twelve_coverage.py
  python scripts/test_twelve_coverage.py --base-url http://localhost:8000 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import httpx


def _client_timeout() -> httpx.Timeout:
    return httpx.Timeout(20.0, connect=5.0)


# (category, symbol, short_label_for_table)
COVERAGE_SYMBOLS: list[tuple[str, str, str]] = [
    ("us_equity", "AAPL", "US equity"),
    ("us_equity", "MSFT", "US equity"),
    ("us_equity", "NVDA", "US equity"),
    ("us_equity", "TSLA", "US equity"),
    ("us_etf", "SPY", "US ETF"),
    ("us_etf", "QQQ", "US ETF"),
    ("index", "SPX", "index"),
    ("index", "^GSPC", "index Yahoo caret"),
    ("index", "^IXIC", "index"),
    ("index", "NDX", "Nasdaq-100 style"),
    ("index", "^DJI", "index"),
    ("index", "DJI", "Dow Jones alt"),
    ("index", "VIX", "volatility"),
    ("crypto", "BTC/USD", "crypto"),
    ("crypto", "ETH/USD", "crypto"),
    ("commodity", "XAU/USD", "gold FX"),
    ("commodity", "GOLD", "gold alt"),
    ("commodity", "XAG/USD", "silver FX"),
    ("commodity", "WTI", "crude"),
    ("commodity", "BRENT", "crude"),
    ("hk", "0700.HK", "Hong Kong"),
    ("hk", "9988.HK", "Hong Kong"),
    ("a_share", "600519.SH", "A-share"),
    ("a_share", "000858.SZ", "A-share"),
    ("futures", "ES", "futures"),
    ("futures", "NQ", "futures"),
    ("futures", "CL", "futures"),
    ("futures", "GC", "futures"),
]


@dataclass
class CoverageRow:
    category: str
    symbol: str
    label: str
    search: str  # success | fail | skip
    quote: str
    time_series: str
    search_data_source: str | None
    quote_data_source: str | None
    time_series_data_source: str | None
    notes: str


def _obtain_token(base: str) -> str | None:
    tok = (os.environ.get("NARRATIVE_TEST_TOKEN") or os.environ.get("TWELVE_COVERAGE_TOKEN") or "").strip()
    if tok:
        return tok
    email = (os.environ.get("NARRATIVE_TEST_EMAIL") or "").strip()
    password = (os.environ.get("NARRATIVE_TEST_PASSWORD") or "").strip()
    if not email or not password:
        return None
    try:
        with httpx.Client(timeout=_client_timeout()) as c:
            r = c.post(f"{base.rstrip('/')}/api/auth/login", json={"email": email, "password": password})
            if r.status_code != 200:
                print(f"[warn] login failed HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
                return None
            return str(r.json().get("access_token") or "")
    except Exception as e:
        print(f"[warn] login error: {e}", file=sys.stderr)
        return None


def _get_json(c: httpx.Client, path: str, headers: dict[str, str]) -> tuple[int, dict[str, Any] | None]:
    try:
        r = c.get(path, headers=headers, timeout=_client_timeout())
        if r.headers.get("content-type", "").startswith("application/json"):
            try:
                return r.status_code, r.json()
            except json.JSONDecodeError:
                return r.status_code, None
        return r.status_code, None
    except Exception as e:
        return -1, {"_error": str(e)}


def _run_row(
    c: httpx.Client,
    base: str,
    category: str,
    symbol: str,
    label: str,
    token: str | None,
) -> CoverageRow:
    notes: list[str] = []
    h_auth: dict[str, str] = {}
    if token:
        h_auth["Authorization"] = f"Bearer {token}"

    # --- search ---
    search_st = "skip"
    search_ds: str | None = None
    if token:
        q_enc = quote(symbol, safe="")
        path = f"{base.rstrip('/')}/api/market/search?q={q_enc}"
        status, body = _get_json(c, path, h_auth)
        if status == 200 and isinstance(body, dict):
            data = body.get("data")
            search_ds = body.get("data_source")
            if isinstance(data, list) and len(data) > 0:
                search_st = "success"
                if search_ds != "twelvedata" and search_ds != "fallback":
                    notes.append(f"search ds={search_ds}")
            else:
                search_st = "fail"
                notes.append("search empty data")
        else:
            search_st = "fail"
            notes.append(f"search HTTP {status}")
    else:
        notes.append("search skipped (no token)")

    # --- quote ---
    sym_enc = quote(symbol, safe="")
    path_q = f"{base.rstrip('/')}/api/market/quote?symbol={sym_enc}"
    status_q, bq = _get_json(c, path_q, {})
    quote_st = "fail"
    quote_ds: str | None = None
    if status_q == 200 and isinstance(bq, dict):
        quote_ds = bq.get("data_source")
        price = bq.get("price")
        if price is None and isinstance(bq.get("data"), dict):
            price = bq["data"].get("price")
        if price is not None:
            quote_st = "success"
        else:
            notes.append("quote no price")
    else:
        notes.append(f"quote HTTP {status_q}")

    # --- time_series ---
    path_ts = f"{base.rstrip('/')}/api/market/time_series?symbol={sym_enc}&period=1M"
    status_t, bt = _get_json(c, path_ts, {})
    ts_st = "fail"
    ts_ds: str | None = None
    if status_t == 200 and isinstance(bt, dict):
        ts_ds = bt.get("data_source")
        bars = bt.get("bars")
        if bars is None and isinstance(bt.get("data"), dict):
            bars = bt["data"].get("bars")
        if isinstance(bars, list) and len(bars) > 0:
            ts_st = "success"
        else:
            notes.append("time_series no bars")
    else:
        notes.append(f"time_series HTTP {status_t}")

    # consolidated notes for fallback-only success
    for name, ok, ds in (
        ("quote", quote_st, quote_ds),
        ("time_series", ts_st, ts_ds),
        ("search", search_st, search_ds),
    ):
        if ok == "success" and ds == "fallback":
            notes.append(f"{name} twelvedata=fallback")

    return CoverageRow(
        category=category,
        symbol=symbol,
        label=label,
        search=search_st,
        quote=quote_st,
        time_series=ts_st,
        search_data_source=search_ds,
        quote_data_source=quote_ds,
        time_series_data_source=ts_ds,
        notes="; ".join(dict.fromkeys(notes)) if notes else "",
    )


def _print_table(rows: list[CoverageRow]) -> None:
    cols = ("category", "symbol", "search", "quote", "ts", "src_s", "src_q", "src_ts", "notes")
    w = [10, 14, 7, 7, 7, 10, 10, 10, 40]
    header = f"{'category':<{w[0]}} {'symbol':<{w[1]}} {'search':<{w[2]}} {'quote':<{w[3]}} {'ts':<{w[4]}} {'s_ds':<{w[5]}} {'q_ds':<{w[6]}} {'ts_ds':<{w[7]}} notes"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r.category:<{w[0]}} {r.symbol:<{w[1]}} {r.search:<{w[2]}} {r.quote:<{w[3]}} {r.time_series:<{w[4]}} "
            f"{str(r.search_data_source or '-'):<{w[5]}} {str(r.quote_data_source or '-'):<{w[6]}} "
            f"{str(r.time_series_data_source or '-'):<{w[7]}} {r.notes}"
        )


def _summarize(rows: list[CoverageRow]) -> None:
    by_cat: dict[str, list[CoverageRow]] = {}
    for r in rows:
        by_cat.setdefault(r.category, []).append(r)

    def _rate(cat_rows: list[CoverageRow], field: str) -> tuple[int, int]:
        ok = sum(1 for x in cat_rows if getattr(x, field) == "success")
        att = sum(1 for x in cat_rows if getattr(x, field) != "skip")
        return ok, max(att, 1)

    print("\n=== Category rollup (success count / attempted; search excludes skipped) ===")
    for cat in sorted(by_cat.keys()):
        rs = by_cat[cat]
        s_ok, s_n = _rate(rs, "search")
        q_ok, q_n = _rate(rs, "quote")
        t_ok, t_n = _rate(rs, "time_series")
        tw_q = sum(1 for x in rs if x.quote == "success" and x.quote_data_source == "twelvedata")
        tw_t = sum(1 for x in rs if x.time_series == "success" and x.time_series_data_source == "twelvedata")
        print(
            f"  {cat}: search {s_ok}/{s_n} | quote {q_ok}/{q_n} (twelve {tw_q}/{q_n}) | "
            f"time_series {t_ok}/{t_n} (twelve {tw_t}/{t_n})"
        )

    print("\n=== Manual interpretation (re-run after setting TWELVE_API_KEY on backend) ===")
    print(
        "1) Twelve 明显适合作主源：美股/主流 ETF 等若 quote+time_series 多为 twelvedata 且成功率高。\n"
        "2) 仅部分支持：指数多空格式（^GSPC vs SPX）、港股/A 股后缀、商品/期货符号等，易出现单项失败或仅 fallback。\n"
        "3) 应继续 fallback / 单独数据源：quote 或 K 线长期空、仅靠快照的类别。\n"
        "4) Symbol 映射：同标的不同写法成功率差异大时，需要 Twelve 专用映射层而非各处硬编码。"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Twelve + /api/market/* coverage smoke test")
    p.add_argument("--base-url", default=os.environ.get("NARRATIVE_TEST_BASE", "http://127.0.0.1:8000"))
    p.add_argument("--json", action="store_true", help="Print JSON only")
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    token = _obtain_token(base)
    if not token:
        print(
            "[info] No auth: set NARRATIVE_TEST_TOKEN or NARRATIVE_TEST_EMAIL+NARRATIVE_TEST_PASSWORD "
            "to test /api/market/search.",
            file=sys.stderr,
        )

    rows: list[CoverageRow] = []
    with httpx.Client(timeout=_client_timeout()) as client:
        for category, symbol, label in COVERAGE_SYMBOLS:
            rows.append(_run_row(client, base, category, symbol, label, token))

    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2))
    else:
        _print_table(rows)
        _summarize(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
