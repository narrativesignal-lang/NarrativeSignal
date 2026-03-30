from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
import urllib.request

import feedparser

from app.services.macro_news_dedup import ensure_utc, finalize_macro_news_list
from app.services.external_api_stats import bump as bump_external
from app.services.publisher_tier import publisher_tier_and_normalized

logger = logging.getLogger(__name__)

_FEED_FETCH_TIMEOUT_SEC = 6.0
_FEED_BATCH_WAIT_SEC = 22.0
_FEED_MAX_WORKERS = 10
_FEED_USER_AGENT = "Mozilla/5.0 (compatible; NarrativeMacroNews/1.0)"


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
  publisher_tier: int = 3
  publisher_normalized: str | None = None
  duplicate_count: int = 1
  related_publishers: list[str] = field(default_factory=list)


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
  """Build Google News RSS URL (English, US). `when:2d` ≈ 48h lookback for the query."""
  encoded = quote_plus(q)
  return f"https://news.google.com/rss/search?q={encoded}+when:2d&hl=en-US&gl=US&ceid=US:en"


_GOOGLE_NEWS_HOST = "news.google.com"


_HUB_SINGLE_SEGMENTS = frozenset(
  {
    "us",
    "en",
    "opinion",
    "world",
    "markets",
    "politics",
    "business",
    "tech",
    "economy",
    "finance",
    "news",
    "home",
    "intl",
  }
)


def _is_likely_homepage_url(url: str | None) -> bool:
  """True if URL looks like site root or a top nav section, not a specific article."""
  if not url or not str(url).strip():
    return True
  try:
    p = urlparse(str(url).strip())
    path = (p.path or "").rstrip("/")
    if path == "":
      return True
    segments = [s for s in path.split("/") if s]
    if len(segments) == 1 and segments[0].lower() in _HUB_SINGLE_SEGMENTS:
      return True
    return False
  except Exception:
    return False


def _feed_source_title(feed: Any) -> str | None:
  ft = getattr(feed, "title", None) if feed is not None else None
  return str(ft).strip() if ft else None


def _entry_source_block(entry: Any) -> dict[str, Any] | None:
  src = entry.get("source") if hasattr(entry, "get") else getattr(entry, "source", None)
  if not src:
    return None
  title = src.get("title") if hasattr(src, "get") else getattr(src, "title", None)
  href = None
  if hasattr(src, "get"):
    href = src.get("href") or src.get("url")
  else:
    href = getattr(src, "href", None) or getattr(src, "url", None)
  out: dict[str, Any] = {}
  if title is not None:
    out["title"] = title
  if href is not None:
    out["href"] = href
  return out or None


def _publisher_from_entry_title(title: str) -> str | None:
  if " - " not in title:
    return None
  return title.rsplit(" - ", 1)[-1].strip() or None


def _first_non_google_href(entry: Any) -> str | None:
  for link in getattr(entry, "links", None) or []:
    href = link.get("href") if isinstance(link, dict) else getattr(link, "href", None)
    if href and _GOOGLE_NEWS_HOST not in href:
      return str(href).strip()
  return None


def _resolve_publisher_and_url(entry: Any, raw_title: str, feed_title: str | None) -> tuple[str, str | None]:
  """Publisher for display; URL preferring a real article path over publisher homepages."""
  src = _entry_source_block(entry)
  pub = None
  from_source_href: str | None = None
  if src:
    st = src.get("title") if isinstance(src, dict) else None
    if st:
      pub = str(st).strip()
    ho = src.get("href") if isinstance(src, dict) else getattr(src, "href", None)
    if ho and _GOOGLE_NEWS_HOST not in str(ho):
      from_source_href = str(ho).strip()

  if not pub:
    pub = _publisher_from_entry_title(raw_title)
  if not pub and feed_title and feed_title.lower() != "google news":
    pub = feed_title
  if not pub:
    pub = "News"

  link = getattr(entry, "link", None)
  link_s = str(link).strip() if link else None

  # Prefer non-Google article links from <entry>; then non-home direct URLs; then Google redirect.
  original = _first_non_google_href(entry)
  if not original and from_source_href and not _is_likely_homepage_url(from_source_href):
    original = from_source_href
  if not original and link_s and _GOOGLE_NEWS_HOST not in link_s and not _is_likely_homepage_url(link_s):
    original = link_s
  if not original and link_s:
    original = link_s
  if not original and from_source_href:
    original = from_source_href

  return pub, original


def _clean_display_title(raw_title: str, publisher: str) -> str:
  suffix = f" - {publisher}"
  if publisher and raw_title.endswith(suffix):
    return raw_title[: -len(suffix)].strip()
  return raw_title


def _plain_summary(raw: str | None, title: str, max_len: int = 220) -> str | None:
  """Strip HTML, collapse whitespace, cap length. Omit when text is only duplicating the headline."""
  def clip(s: str) -> str:
    s = s.strip()
    if len(s) <= max_len:
      return s
    return s[: max_len - 1] + "…"

  def _too_close_to_title(body: str, headline: str) -> bool:
    b = re.sub(r"\s+", " ", body.strip().lower())
    h = re.sub(r"\s+", " ", headline.strip().lower())
    if not b or not h:
      return False
    if b == h:
      return True
    if b.startswith(h) and len(b) <= len(h) + 20:
      return True
    if h.startswith(b) and len(b) < 40:
      return True
    return False

  if raw:
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    if text and not _too_close_to_title(text, title):
      return clip(text)

  return None


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


def _fetch_feed_xml(feed_url: str, timeout: float) -> bytes | None:
  try:
    req = urllib.request.Request(feed_url, headers={"User-Agent": _FEED_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      return resp.read()
  except (URLError, HTTPError, TimeoutError, OSError, ValueError) as e:
    logger.warning("macro news: feed fetch failed (%s): %s", feed_url[:96], e)
    return None


def _items_from_parsed_feed(
  category: str,
  sub: str,
  parsed: Any,
  *,
  now: datetime,
  cutoff: datetime,
) -> list[MacroNewsItem]:
  feed_title = _feed_source_title(getattr(parsed, "feed", None))
  out: list[MacroNewsItem] = []
  for entry in getattr(parsed, "entries", [])[:100]:
    raw_title = getattr(entry, "title", None)
    if not raw_title:
      continue
    raw_title = str(raw_title).strip()

    published: datetime | None = None
    pp = getattr(entry, "published_parsed", None)
    if pp:
      try:
        published = datetime(
          int(pp[0]),
          int(pp[1]),
          int(pp[2]),
          int(pp[3]),
          int(pp[4]),
          int(pp[5]),
          tzinfo=timezone.utc,
        )
      except (TypeError, ValueError, IndexError):
        published = None
    if not published:
      published = now
    published = ensure_utc(published)
    if published < cutoff:
      continue

    publisher, article_url = _resolve_publisher_and_url(entry, raw_title, feed_title)
    tier, pub_norm = publisher_tier_and_normalized(publisher)
    display_title = _clean_display_title(raw_title, publisher)
    summary_raw = getattr(entry, "summary", None) or getattr(entry, "description", None)
    summary = _plain_summary(
      str(summary_raw) if summary_raw else None,
      display_title or raw_title,
    )
    link_for_id = getattr(entry, "link", None) or article_url or ""

    out.append(
      MacroNewsItem(
        id=f"{category}:{sub}:{hash((display_title or raw_title) + (article_url or '') + (link_for_id or ''))}",
        title=display_title or raw_title,
        source=publisher,
        timestamp=published,
        url=article_url,
        category=category,
        subcategory=sub,
        summary=summary,
        sentiment=None,
        impact=None,
        publisher_tier=tier,
        publisher_normalized=pub_norm,
      )
    )
  return out


def _items_from_feed_url(
  category: str,
  sub: str,
  feed_url: str,
  *,
  now: datetime,
  cutoff: datetime,
  timeout: float,
) -> list[MacroNewsItem]:
  raw = _fetch_feed_xml(feed_url, timeout)
  if not raw:
    return []
  try:
    parsed = feedparser.parse(raw)
  except Exception as e:
    logger.warning("macro news: feed parse failed (%s): %s", feed_url[:96], e)
    return []
  return _items_from_parsed_feed(category, sub, parsed, now=now, cutoff=cutoff)


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
  - Collapses near-duplicate stories (URL + normalized title + fuzzy match), keeping the best
    source by impact, publisher tier, direct URL, then recency; then sorts for display.
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

  bump_external("macro_rss_feed", len(pairs))

  cutoff = now - timedelta(hours=48)
  items: list[MacroNewsItem] = []

  workers = min(_FEED_MAX_WORKERS, max(1, len(pairs)))
  executor = ThreadPoolExecutor(max_workers=workers)
  try:
    futures = [
      executor.submit(
        _items_from_feed_url,
        category,
        sub,
        feed_url,
        now=now,
        cutoff=cutoff,
        timeout=_FEED_FETCH_TIMEOUT_SEC,
      )
      for sub, feed_url in pairs
    ]
    done, _pending = wait(futures, timeout=_FEED_BATCH_WAIT_SEC)
    for fut in done:
      try:
        items.extend(fut.result())
      except Exception as e:
        logger.warning("macro news: feed task failed: %s", e)
  finally:
    executor.shutdown(wait=False, cancel_futures=True)

  try:
    final_list = finalize_macro_news_list(items, limit)
  except Exception as e:
    logger.warning("macro news: dedup/sort failed, using recency cap: %s", e)
    items.sort(key=lambda x: ensure_utc(x.timestamp), reverse=True)
    final_list = items[:limit]

  _CACHE[key] = (now, final_list)
  return final_list

