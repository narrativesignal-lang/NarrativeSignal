from __future__ import annotations

import re
import unicodedata

# Canonical match keys are lowercase, no apostrophes, single spaces.
# DISPLAY names are Title Case / brand styling for API `publisher_normalized`.

_CANONICAL_DISPLAY: dict[str, str] = {
  "bloomberg": "Bloomberg",
  "reuters": "Reuters",
  "cnbc": "CNBC",
  "wall street journal": "Wall Street Journal",
  "financial times": "Financial Times",
  "yahoo finance": "Yahoo Finance",
  "marketwatch": "MarketWatch",
  "barrons": "Barron's",
  "associated press": "Associated Press",
  "the new york times": "The New York Times",
  "the washington post": "The Washington Post",
  "bbc": "BBC",
  "cnn": "CNN",
  "techcrunch": "TechCrunch",
  "the verge": "The Verge",
  "coindesk": "CoinDesk",
  "decrypt": "Decrypt",
  "investing": "Investing.com",
  "business insider": "Business Insider",
  "fortune": "Fortune",
  "the information": "The Information",
  "seeking alpha": "Seeking Alpha",
  "motley fool": "Motley Fool",
  "benzinga": "Benzinga",
  "the block": "The Block",
  "axios": "Axios",
  "politico": "Politico",
  "nikkei asia": "Nikkei Asia",
}

TIER_1_KEYS: frozenset[str] = frozenset(
  {
    "bloomberg",
    "reuters",
    "cnbc",
    "wall street journal",
    "financial times",
    "yahoo finance",
    "marketwatch",
    "barrons",
    "associated press",
    "the new york times",
    "the washington post",
    "bbc",
    "cnn",
  }
)

TIER_2_KEYS: frozenset[str] = frozenset(
  {
    "techcrunch",
    "the verge",
    "coindesk",
    "decrypt",
    "investing",
    "business insider",
    "fortune",
    "the information",
    "seeking alpha",
    "motley fool",
    "benzinga",
    "the block",
    "axios",
    "politico",
    "nikkei asia",
  }
)

# Normalized alias -> canonical match key (must exist in _CANONICAL_DISPLAY)
_ALIASES: dict[str, str] = {
  "wsj": "wall street journal",
  "wall st journal": "wall street journal",
  "the wsj": "wall street journal",
  "ft": "financial times",
  "the ft": "financial times",
  "financialtimes": "financial times",
  "nyt": "the new york times",
  "new york times": "the new york times",
  "ny times": "the new york times",
  "n.y. times": "the new york times",
  "wapo": "the washington post",
  "washington post": "the washington post",
  "bbc news": "bbc",
  "bbc.com": "bbc",
  "bbc news uk": "bbc",
  "cnn business": "cnn",
  "cnn.com": "cnn",
  "ap": "associated press",
  "ap news": "associated press",
  "apnews": "associated press",
  "reuters india": "reuters",
  "reuters africa": "reuters",
  "yahoo! finance": "yahoo finance",
  "yahoo finance canada": "yahoo finance",
  "bloomberg news": "bloomberg",
  "bloomberg.com": "bloomberg",
  "reuters.com": "reuters",
  "cnbc.com": "cnbc",
  "marketwatch.com": "marketwatch",
  "ft.com": "financial times",
  "the financial times": "financial times",
  "cnn politics": "cnn",
  "cnn international": "cnn",
  "the associated press": "associated press",
  "washington post": "the washington post",
  "tech crunch": "techcrunch",
  "verge": "the verge",
  "theverge": "the verge",
  "benzinga.com": "benzinga",
  "benzinga pro": "benzinga",
  "seekingalpha": "seeking alpha",
  "businessinsider": "business insider",
  "fortune magazine": "fortune",
  "axios news": "axios",
  "the motley fool": "motley fool",
  "fool.com": "motley fool",
  "coindesk.com": "coindesk",
  "decrypt.co": "decrypt",
  "investing.com": "investing",
  "nikkei": "nikkei asia",
  "nikkei.com": "nikkei asia",
  "the block crypto": "the block",
}


def _nfkc(s: str) -> str:
  return unicodedata.normalize("NFKC", s)


def normalize_publisher_label(raw: str) -> str:
  """
  Normalize for tier matching: lowercase, NFKC, strip apostrophe-like chars,
  collapse whitespace, strip light trailing punctuation.
  """
  if not raw:
    return ""
  t = _nfkc(raw.strip().lower())
  t = t.replace("’", "").replace("'", "").replace("`", "")
  t = re.sub(r"\s+", " ", t).strip()
  t = re.sub(r"[|,]+", " ", t)
  t = re.sub(r"\s+", " ", t).strip()
  # Drop common trailing domain for single-token brands: "bloomberg.com" -> "bloomberg"
  t = re.sub(
    r"\.(com|net|org|co|io|uk|us)\s*$",
    "",
    t,
    flags=re.IGNORECASE,
  ).strip()
  t = re.sub(r"\s+", " ", t).strip()
  return t


def _strip_noise_suffixes(key: str) -> str:
  n = key
  for suffix in (
    " news",
    " - news",
    " | reuters",
    " breaking news",
    " latest news",
  ):
    if n.endswith(suffix) and len(n) > len(suffix):
      n = n[: -len(suffix)].strip()
  return n


def _resolve_canonical_key(normalized: str) -> str | None:
  if not normalized:
    return None
  if normalized in TIER_1_KEYS or normalized in TIER_2_KEYS:
    return normalized
  if normalized in _ALIASES:
    return _ALIASES[normalized]
  n2 = _strip_noise_suffixes(normalized)
  if n2 != normalized:
    if n2 in TIER_1_KEYS or n2 in TIER_2_KEYS:
      return n2
    if n2 in _ALIASES:
      return _ALIASES[n2]
  return None


def publisher_tier_and_normalized(display_source: str) -> tuple[int, str | None]:
  """
  Returns (tier 1..3, publisher_normalized).

  `publisher_normalized` is a canonical display label when matched to tier lists/aliases;
  otherwise None (caller may omit or use raw `source`).
  """
  norm = normalize_publisher_label(display_source)
  if not norm:
    return 3, None

  canonical = _resolve_canonical_key(norm)
  if not canonical:
    return 3, None

  display = _CANONICAL_DISPLAY.get(canonical, display_source.strip())
  if canonical in TIER_1_KEYS:
    return 1, display
  if canonical in TIER_2_KEYS:
    return 2, display
  return 3, None
