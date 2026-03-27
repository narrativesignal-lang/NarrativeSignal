from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import quote_plus

import feedparser


@dataclass
class MacroNewsItem:
  id: str
  title: str
  source: str
  timestamp: datetime
  url: str | None
  category: str
  subcategory: str
  summary: str | None = None
  sentiment: str | None = None
  impact: float | None = None


# --- Category / subcategory → feed / query mapping ---

GENERAL_KEYWORDS: dict[str, list[str]] = {
  "AI": ["artificial intelligence", "AI technology", "machine learning"],
  "Rates": ["interest rates", "federal reserve", "bond yields"],
  "Inflation": ["inflation", "cpi inflation", "ppi inflation"],
  "Energy": ["energy markets", "oil prices", "natural gas"],
  "China": ["china economy", "china markets", "china stocks"],
  "Geopolitics": ["geopolitics", "geopolitical risk", "geopolitical tensions"],
  "Regulation": ["financial regulation", "market regulation"],
  "Consumer": ["consumer spending", "retail sales", "consumer confidence"],
  "Labor": ["labor market", "unemployment", "jobs report"],
  "Banking": ["banking sector", "banks", "bank earnings"],
}

STOCK_KEYWORDS: dict[str, list[str]] = {
  "Semiconductors": ["semiconductor stocks", "chipmakers", "gpu chips"],
  "Software": ["software stocks", "enterprise software", "saas"],
  "Internet": ["internet stocks", "online platforms", "social media companies"],
  "Consumer Electronics": ["consumer electronics", "smartphones", "hardware makers"],
  "Auto Manufacturers": ["auto manufacturers", "electric vehicles", "EV makers"],
  "Aerospace & Defense": ["aerospace and defense", "defense contractors"],
  "Utilities": ["utilities sector", "utility stocks"],
  "Banks": ["bank stocks", "financials sector"],
  "Biotech": ["biotech stocks", "biotechnology companies"],
  "Oil & Gas": ["oil and gas stocks", "energy producers"],
  "Retail": ["retail stocks", "retailers"],
  "Industrials": ["industrial stocks", "manufacturing sector"],
}

FUTURES_KEYWORDS: dict[str, list[str]] = {
  "Precious Metals": ["gold futures", "silver futures", "precious metals"],
  "Energy": ["crude oil futures", "natural gas futures", "energy futures"],
  "Industrial Metals": ["copper futures", "aluminium futures", "industrial metals"],
  "Agriculture": ["grain futures", "corn futures", "wheat futures"],
  "Softs": ["coffee futures", "sugar futures", "soft commodities"],
  "Livestock": ["cattle futures", "hog futures", "livestock futures"],
  "Rates": ["bond futures", "interest rate futures"],
  "FX": ["currency futures", "fx futures", "forex futures"],
}

CRYPTO_KEYWORDS: dict[str, list[str]] = {
  "BTC": ["bitcoin", "BTC price"],
  "ETH": ["ethereum", "ETH price"],
  "SOL": ["solana crypto", "SOL price"],
  "XRP": ["xrp crypto", "ripple token"],
  "BNB": ["binance coin", "BNB token"],
  "DOGE": ["dogecoin", "DOGE meme coin"],
  "ADA": ["cardano", "ADA crypto"],
}


CATEGORY_KEYWORDS: dict[str, dict[str, list[str]]] = {
  "general": GENERAL_KEYWORDS,
  "stock": STOCK_KEYWORDS,
  "futures": FUTURES_KEYWORDS,
  "crypto": CRYPTO_KEYWORDS,
}


def _google_news_rss_for_query(q: str) -> str:
  """
  Build a simple Google News RSS URL for a query.
  We keep it conservative (English, US) and 24h lookback.
  """
  encoded = quote_plus(q)
  return f"https://news.google.com/rss/search?q={encoded}+when:24h&hl=en-US&gl=US&ceid=US:en"


def _feeds_for(category: str, subcategory: str | None) -> list[tuple[str, str]]:
  """
  Return a list of (subcategory, feed_url) pairs for the requested category / subcategory.
  """
  slug = category.lower()
  mapping = CATEGORY_KEYWORDS.get(slug, {})
  if not mapping:
    return []

  pairs: list[tuple[str, str]] = []
  if subcategory and subcategory in mapping:
    keys = [subcategory]
  else:
    keys = list(mapping.keys())

  for sub in keys:
    for kw in mapping.get(sub, []):
      pairs.append((sub, _google_news_rss_for_query(kw)))
  return pairs


_CACHE: dict[tuple[str, str | None, int], tuple[datetime, list[MacroNewsItem]]] = {}
_CACHE_TTL = timedelta(minutes=5)


def _dedupe_and_sort(items: Iterable[MacroNewsItem], limit: int) -> list[MacroNewsItem]:
  seen_url: set[str] = set()
  seen_title: set[tuple[str, str]] = set()
  deduped: list[MacroNewsItem] = []

  for item in items:
    key_url = (item.url or "").strip().lower()
    if key_url:
      if key_url in seen_url:
        continue
      seen_url.add(key_url)
    else:
      tkey = (item.title.strip().lower(), item.source.strip().lower())
      if tkey in seen_title:
        continue
      seen_title.add(tkey)
    deduped.append(item)

  deduped.sort(key=lambda x: x.timestamp, reverse=True)
  return deduped[:limit]


def fetch_macro_news(
  *,
  category: str,
  subcategory: str | None,
  limit: int = 40,
) -> list[MacroNewsItem]:
  """
  Fetch macro news from Google News RSS for the given category / subcategory.

  - Uses category/subcategory keyword mapping.
  - Caches results for a short TTL to avoid hammering upstream feeds.
  - Deduplicates by URL (or title+source) and sorts newest first.
  """
  key = (category.lower(), subcategory, limit)
  now = datetime.now(timezone.utc)
  cached = _CACHE.get(key)
  if cached and now - cached[0] < _CACHE_TTL:
    return cached[1]

  pairs = _feeds_for(category, subcategory)
  if not pairs:
    _CACHE[key] = (now, [])
    return []

  cutoff = now - timedelta(hours=48)
  items: list[MacroNewsItem] = []

  for sub, feed_url in pairs:
    parsed = feedparser.parse(feed_url)
    for entry in parsed.entries[:100]:
      link = getattr(entry, "link", None)
      title = getattr(entry, "title", None)
      if not title:
        continue

      published = None
      if getattr(entry, "published_parsed", None):
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
      if not published:
        published = now
      if published < cutoff:
        continue

      source_title = getattr(getattr(parsed, "feed", None), "title", None) or "News"
      summary = getattr(entry, "summary", None)

      item = MacroNewsItem(
        id=f"{category}:{sub}:{hash((title or '') + (link or ''))}",
        title=title,
        source=source_title,
        timestamp=published,
        url=link,
        category=category,
        subcategory=sub,
        summary=summary,
        sentiment=None,
        impact=None,
      )
      items.append(item)

  deduped = _dedupe_and_sort(items, limit)
  _CACHE[key] = (now, deduped)
  return deduped

